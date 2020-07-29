import time
from flask_sqlalchemy import SQLAlchemy
import flask_login
import passlib.hash
import logging
import datetime
from werkzeug.security import gen_salt
from .send_email import sendMail

logger = logging.getLogger('labboxmain')
db = SQLAlchemy()
login_manager = flask_login.LoginManager()
from config import create_rule


class User(db.Model, flask_login.UserMixin):
    __tablename__ = 'user'
    id        = db.Column(db.Integer,     primary_key=True)
    name      = db.Column(db.String(32),  unique=True)
    disable   = db.Column(db.Boolean,     default=False)
    email     = db.Column(db.String(64),  default="")
    password  = db.Column(db.String(300), default=gen_salt(24)) # nullable=False
    passtime  = db.Column(db.DateTime,    default=lambda: datetime.datetime.utcfromtimestamp(0))
    groupid   = db.Column(db.Integer,     default=0, nullable=False)
    quota     = db.Column(db.Integer,     default=0)
    use_quota = db.Column(db.Integer,     default=0)

    def __str__(self):
        return '<User {}>'.format(self.name)

    def checkPassword(self, password):
        return passlib.hash.sha512_crypt.verify(password, self.password)

    def getGroupData(self):
        return create_rule(self)

    def setPassword(self, password, record=True):
        self.password = passlib.hash.sha512_crypt.hash(password)
        if record:
            self.passtime = datetime.datetime.utcnow()
        db.session.commit()

    # for oauth
    def get_user_id(self):
        return self.id


def setPW(user, newone):
    user.setPassword(newone, record=True)
    from .box import boxesPasswd
    boxesPasswd(user)


@login_manager.user_loader
def user_loader(id):
    return User.query.get(id)


def getUserId(name, password):
    u = User.query.filter_by(name=name).first()
    if not u:
        return None
    if not u.checkPassword(password):
        return None
    return user_loader(u.id)


def add_user(name, passwd='', groupid=0, quota=0, email=""):
    """ Add user by this function """
    name = name.strip()
    assert(name)
    logger.info('[Database] Add user ' + name)
    u = User.query.filter_by(name=name).first()
    assert(not u)
    u = User(name=name,
             groupid=groupid,
             quota=quota,
             email="")
    u.setPassword(passwd)
    u.passtime = datetime.datetime.utcfromtimestamp(0)
    db.session.add(u)
    db.session.commit()
    return name


def sendUserMail(user, template):
    """ reset password and send email """
    password = gen_salt(48)
    user.setPassword(password)
    user.passtime = datetime.datetime.utcfromtimestamp(0)
    return sendMail(user.email, template, name=user.name, password=password)


def add_user_by_email(name, email="", groupid=0, quota=0):
    """ Add user by this function, it will notify the user by email."""
    name = name.strip()
    assert(name)
    logger.info('[Database] Add user ' + name)
    u = User.query.filter_by(name=name).first()
    assert(not u)
    u = User(name=name,
             disable=False,
             groupid=groupid,
             quota=quota,
             email=email)
    if email:
        sendUserMail(u, "register")
    db.session.add(u)
    db.session.commit()
    return name


def forgetPassword(email):
    """ Reset password and sent email """
    u = User.query.filter_by(email=email).first()
    assert(u)
    sendUserMail(u, "forgetpass")
    db.session.commit()
    return u.name
