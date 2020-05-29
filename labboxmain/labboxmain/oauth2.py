# authlib 0.14.1
import time
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.sqla_oauth2 import (
    OAuth2ClientMixin,
    OAuth2AuthorizationCodeMixin,
    OAuth2TokenMixin,
    create_query_client_func,
    create_save_token_func,
    create_revocation_endpoint,
    create_bearer_token_validator,
)
from authlib.integrations.flask_oauth2 import (
    AuthorizationServer,
    ResourceProtector,
    current_token
)
from authlib.oauth2.rfc6749 import grants
from werkzeug.security import gen_salt
import flask_login
from flask import Blueprint, request, render_template, jsonify, abort
import logging
from .models import User, db


logger = logging.getLogger('labboxmain')
bp = Blueprint(__name__, 'oauth')


class OAuth2Client(db.Model, OAuth2ClientMixin):
    __tablename__ = 'oauth2_client'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class OAuth2AuthorizationCode(db.Model, OAuth2AuthorizationCodeMixin):
    __tablename__ = 'oauth2_code'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class OAuth2Token(db.Model, OAuth2TokenMixin):
    __tablename__ = 'oauth2_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')

    def is_refresh_token_active(self):
        if self.revoked:
            return False
        expires_at = self.issued_at + self.expires_in * 2
        return expires_at >= time.time()


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    def create_authorization_code(self, client, grant_user, request):
        code = gen_salt(48)
        item = OAuth2AuthorizationCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            user_id=grant_user.id,
        )
        db.session.add(item)
        db.session.commit()
        return code

    def parse_authorization_code(self, code, client):
        item = OAuth2AuthorizationCode.query.filter_by(
            code=code, client_id=client.client_id).first()
        if item and not item.is_expired():
            return item

    def delete_authorization_code(self, authorization_code):
        db.session.delete(authorization_code)
        db.session.commit()

    def authenticate_user(self, authorization_code):
        return User.query.get(authorization_code.user_id)


class PasswordGrant(grants.ResourceOwnerPasswordCredentialsGrant):
    def authenticate_user(self, username, password):
        user = User.query.filter_by(name=username).first()
        if user is not None and user.checkPassword(password):
            return user


class RefreshTokenGrant(grants.RefreshTokenGrant):
    def authenticate_refresh_token(self, refresh_token):
        token = OAuth2Token.query.filter_by(refresh_token=refresh_token).first()
        if token and token.is_refresh_token_active():
            return token

    def authenticate_user(self, credential):
        return User.query.get(credential.user_id)

    def revoke_old_credential(self, credential):
        credential.revoked = True
        db.session.add(credential)
        db.session.commit()


query_client = create_query_client_func(db.session, OAuth2Client)
save_token = create_save_token_func(db.session, OAuth2Token)
authorization = AuthorizationServer(
    query_client=query_client,
    save_token=save_token,
)
require_oauth = ResourceProtector()


def config_oauth(app, dn='', url_prefix="/oauth"):
    bp.domain_name = dn
    authorization.init_app(app)

    # support all grants
    authorization.register_grant(grants.ImplicitGrant)
    authorization.register_grant(grants.ClientCredentialsGrant)
    authorization.register_grant(AuthorizationCodeGrant)
    authorization.register_grant(PasswordGrant)
    authorization.register_grant(RefreshTokenGrant)

    # support revocation
    revocation_cls = create_revocation_endpoint(db.session, OAuth2Token)
    authorization.register_endpoint(revocation_cls)

    # protect resource
    bearer_cls = create_bearer_token_validator(db.session, OAuth2Token)
    require_oauth.register_token_validator(bearer_cls())

    # main
    app.register_blueprint(bp, url_prefix=url_prefix)


def split_by_crlf(s):
    return [v for v in s.splitlines() if v]


@bp.route('/client', methods=['GET', 'POST'])
@flask_login.login_required
def client():
    ''' An Interface to control oauth by admin '''
    now_user = flask_login.current_user
    if now_user.groupid != 0:  # admin
        abort(401)
    logger.debug('[oauth] client ' + now_user.name)

    if request.method == 'POST':
        clientCreate(request.form, now_user)
    return render_template('clients.html', clients=OAuth2Client.query.all())


def clientCreate(form, user):
    if form.get('delete_client_id'):
        logger.debug('[oauth] oauth client delete by ' + user.name)
        db.session.delete(OAuth2Client.query.filter_by(
                          client_id=form['delete_client_id']).first())
        db.session.commit()
        return

    client_id = gen_salt(24)
    client_id_issued_at = int(time.time())
    client = OAuth2Client(
        client_id=client_id,
        client_id_issued_at=client_id_issued_at,
        user_id=user.id,
    )

    if client.token_endpoint_auth_method == 'none':
        client.client_secret = ''
    else:
        client.client_secret = gen_salt(48)

    form = request.form
    client_metadata = {
        "client_name": form["client_name"],
        "client_uri": form["client_uri"],
        "grant_types": split_by_crlf(form["grant_type"]),
        "redirect_uris": split_by_crlf(form["redirect_uri"]),
        "response_types": split_by_crlf(form["response_type"]),
        "scope": form["scope"],
        "token_endpoint_auth_method": form["token_endpoint_auth_method"]
    }
    logger.debug('[oauth] oauth client created by ' + user.name)
    client.set_client_metadata(client_metadata)
    db.session.add(client)
    db.session.commit()
    return render_template('clients.html', clients=OAuth2Client.query.all())


@bp.route('/authorize', methods=['GET', 'POST'])
@flask_login.login_required
def authorize():
    '''
    Need to ask grant and confirmed again, but I'm lazy
    # grant = server.validate_consent_request(end_user=user)
    '''
    logger.debug('[oauth] auth ' + str(request.form))
    now_user = flask_login.current_user
    grant_user = authorization.validate_consent_request(end_user=now_user)
    return authorization.create_authorization_response(grant_user=now_user)


@bp.route('/token', methods=['POST'])
def issue_token():
    logger.debug('[oauth] token ' + str(request.form))
    return authorization.create_token_response()


@bp.route('/revoke', methods=['POST'])
def revoke_token():
    return authorization.create_endpoint_response('revocation')


@bp.route('/profile')
@require_oauth('profile')
def profile():
    user = current_token.user
    name = user.name
    logger.debug('[oauth] user ' + name)
    return jsonify({
        'id': name,
        'username': name,
        'name': name,
        'email': name + '@' + bp.domain_name})
