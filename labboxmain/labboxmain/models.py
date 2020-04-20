import time
from flask_sqlalchemy import SQLAlchemy
import flask_login
import passlib.hash
import logging

logger = logging.getLogger('labboxmain')
db = SQLAlchemy()
login_manager = flask_login.LoginManager()


class User(db.Model, flask_login.UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True)
    password = db.Column(db.String(300), nullable=False)
    passtime = db.Column(db.Float, default=0)
    groupid = db.Column(db.Integer, default=0, nullable=False)
    quota = db.Column(db.Integer, default=0)
    use_quota = db.Column(db.Integer, default=0)

    def __str__(self):
        return '<User {}>'.format(self.name)

    def checkPassword(self, password):
        return passlib.hash.sha512_crypt.verify(password, self.password)

    def setPassword(self, password, record=True):
        self.password = passlib.hash.sha512_crypt.hash(password)
        if record:
            self.passtime = time.time()
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


def add_user(name, passwd='', time=0, groupid=0, quota=0):
    logger.info('[Database] Add user ' + name)
    u = User.query.filter_by(name=name).first()
    assert(not u)
    u = User(name=name,
             passtime=time,
             groupid=groupid,
             quota=quota)
    u.setPassword(passwd)
    db.session.add(u)
    db.session.commit()
    return name
