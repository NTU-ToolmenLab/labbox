# authlib 0.11
from authlib.flask.oauth2 import (
    AuthorizationServer,
    ResourceProtector,
    current_token
)
from authlib.common.security import generate_token
from authlib.flask.oauth2.sqla import (
    OAuth2ClientMixin,
    OAuth2TokenMixin,
    OAuth2AuthorizationCodeMixin,
    create_query_client_func,
    create_save_token_func,
    create_bearer_token_validator,
    create_revocation_endpoint,
)
from authlib.oauth2.rfc6749 import grants

import flask_login
from flask import Blueprint, request, render_template, jsonify, abort
import logging
from .models import db, User


logger = logging.getLogger('labboxmain')
bp = Blueprint(__name__, 'oauth')
domain_name = ''
require_oauth = ResourceProtector()
server = AuthorizationServer()


class Client(db.Model, OAuth2ClientMixin):
    __tablename__ = 'oauth2_client'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class Token(db.Model, OAuth2TokenMixin):
    __tablename__ = 'oauth2_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')

    def is_refresh_token_expired(self):
        expires_at = self.issued_at + self.expires_in
        return expires_at < time.time()


class AuthorizationCode(db.Model, OAuth2AuthorizationCodeMixin):
    __tablename__ = 'oauth2_code'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    # no NONE method
    TOKEN_ENDPOINT_AUTH_METHODS = ['client_secret_basic', 'client_secret_post']

    def create_authorization_code(self, client, user, request):
        code = generate_token(48)
        item = AuthorizationCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            user_id=user.id,
        )
        db.session.add(item)
        db.session.commit()
        return code

    def parse_authorization_code(self, code, client):
        item = AuthorizationCode.query.filter_by(
            code=code, client_id=client.client_id).first()
        if item and not item.is_expired():
            return item

    def delete_authorization_code(self, authorization_code):
        db.session.delete(authorization_code)
        db.session.commit()

    def authenticate_user(self, authorization_code):
        return User.query.get(authorization_code.user_id)


def config_oauth(app, dn=''):
    global domain_name
    domain_name = dn
    query_client = create_query_client_func(db.session, Client)
    save_token = create_save_token_func(db.session, Token)
    server.init_app(
        app, query_client=query_client, save_token=save_token
    )
    server.register_grant(AuthorizationCodeGrant)
    server.register_grant(grants.ImplicitGrant)

    # support revocation
    RevocationEndpoint = create_revocation_endpoint(db.session, Token)
    server.register_endpoint(RevocationEndpoint)

    # protect resource
    BearerTokenValidator = create_bearer_token_validator(db.session, Token)
    require_oauth.register_token_validator(BearerTokenValidator())

    # reigster
    app.register_blueprint(bp, url_prefix='/oauth')


@bp.route('/client', methods=['GET', 'POST'])
@flask_login.login_required
def client():
    ''' An Interface to control oauth by admin '''
    now_user = flask_login.current_user
    if now_user.groupid != 1:
        abort(401)
    logger.debug('[oauth] client ' + now_user.name)

    if request.method == 'GET':
        return render_template('clients.html', clients=Client.query.all())
    clientCreate(request.form, now_user)
    return render_template('clients.html', clients=Client.query.all())


def clientCreate(form, user):
    if form.get('delete_client_id'):
        logger.debug('[oauth] oauth client delete by ' + user.name)
        db.session.delete(Client.query.filter_by(
                          client_id=form['delete_client_id']).first())
        db.session.commit()
        return
    logger.debug('[oauth] oauth client created by ' + user.name)
    client = Client(**form.to_dict(flat=True))
    client.user_id = user.id
    client.client_id = generate_token(24)
    if client.token_endpoint_auth_method == 'none':
        client.client_secret = ''
    else:
        client.client_secret = generate_token(48)
    db.session.add(client)
    db.session.commit()


@bp.route('/token', methods=['POST'])
def issue_token():
    logger.debug('[oauth] token ' + str(request.form))
    return server.create_token_response()


@bp.route('/authorize')
@flask_login.login_required
def authorize():
    '''
    Need to ask grant and confirmed again, but I'm lazy
    # grant = server.validate_consent_request(end_user=user)
    '''
    logger.debug('[oauth] auth ' + str(request.form))
    now_user = flask_login.current_user
    grant = server.validate_consent_request(end_user=now_user)
    return server.create_authorization_response(grant_user=now_user)


@bp.route('/revoke', methods=['POST'])
def revoke_token():
    return server.create_endpoint_response('revocation')


@bp.route('/profile', methods=['GET'])
@require_oauth('profile')
def profile():
    user = current_token.user
    name = user.name
    logger.debug('[oauth] user ' + name)
    return jsonify({
        'id': name,
        'username': name,
        'name': name,
        'email': name + '@' + domain_name})
