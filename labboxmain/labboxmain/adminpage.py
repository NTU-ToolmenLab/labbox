from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from flask import abort
import flask_login
import logging
from .models import User, sendUserMail, db as userdb
from .box_models import Box, Image, db as boxdb
from .box_queue import BoxQueue

logger = logging.getLogger('labboxmain')


class AuthModel(ModelView):
    def is_accessible(self):
        if not flask_login.current_user.is_authenticated:
            abort(400, "Permission Denied")
            return False

        now_user = flask_login.current_user
        if now_user.groupid != 0:
            abort(400, "Permission Denied")
            return False

        logger.warning('[Admin] ' + now_user.name)
        return True


class UserModel(AuthModel):
    column_list = ["id", "name", "disable", "groupid", "email", "passtime", "quota", "use_quota", "password"]

    column_descriptions = {
        'password': "Password(Left empty for forgot or newly create, It will send email to whom)",
        'passtime': "The time for manually changing password(0 = never)"
    }

    def on_model_change(self, form, model, is_created):
        if is_created:
            logger.warning("[Admin] Create for " + model.email)
            sendUserMail(model, "register")
            return
        if not model.password:
            logger.warning("[Admin] Reset Password and sent to " + model.email)
            sendUserMail(model, "forgetpass")
            return
        if not model.password.startswith("$6$"):
            logger.warning("[Admin] Reset Password " + model.email)
            model.setPassword(model.password)


admin = Admin()
admin.add_view(AuthModel(Box, boxdb.session))
admin.add_view(AuthModel(Image, boxdb.session))
admin.add_view(UserModel(User, userdb.session))
admin.add_view(AuthModel(BoxQueue, boxdb.session))
