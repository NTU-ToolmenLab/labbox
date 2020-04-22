from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from flask import abort
import flask_login
import logging
from .models import User, db as userdb
from .box_models import Box, Image, db as boxdb

logger = logging.getLogger('labboxmain')


class AuthModel(ModelView):
    def is_accessible(self):
        if not flask_login.current_user.is_authenticated:
            abort(400, "Permission Denied")
            return False

        now_user = flask_login.current_user
        if now_user.groupid != 1:
            abort(400, "Permission Denied")
            return False

        logger.warning('[Admin] ' + now_user.name)
        return True


class UserModel(AuthModel):
    def on_model_change(self, form, model, is_created):
        if not model.password.startswith("$6$"):
            model.setPassword(model.password)


admin = Admin()
admin.add_view(AuthModel(Box, boxdb.session))
admin.add_view(AuthModel(Image, boxdb.session))
admin.add_view(UserModel(User, userdb.session))
