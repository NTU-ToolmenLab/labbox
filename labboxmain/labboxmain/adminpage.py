from flask import render_template
from .models import User, db as userdb
from .box_models import Box, Image, db as boxdb

models = {'box': {
             'model': Box,
             'db': boxdb},
          'image': {
             'model': Image,
             'db': boxdb},
          'user': {
             'model': User,
             'db': userdb}}


def adminView():
    tables = []
    for m in models:
        tables.append(
            {"name": m,
             "table": [{k: v for k, v in dict(a.__dict__).items()
                        if not k.startswith('_')}
                       for a in models[m]['model'].query.all()]})
    for t in tables:
        if not t['table']:
            t['table'] = [{k: None for k in dict(models[m]['model'].__dict__)
                           if not k.startswith('_')}]
    return render_template('adminpage.html', tables=tables)


def adminSet(form):
    # parse form
    if form.get('table') not in models:
        return adminView()
    formwords = {i: form[i].strip() for i in form
                 if i not in ['table', 'method']}
    print(formwords)

    cls = models[form['table']]['model']
    db = models[form['table']]['db']

    acls = cls.query.filter_by(id=int(formwords['id'])).first()
    if form['method'] == 'delete':
        db.session.delete(acls)
        db.session.commit()
    elif form['method'] == 'add':
        modify = 1
        if not acls:
            acls = cls()
            modify = 0
        # print(cls.__table__.columns.items())
        for i in cls.__table__.columns.items():
            if not formwords[i[0]]:
                continue
            if i[0] == 'password':
                acls.setPassword(formwords[i[0]])
            else:
                setattr(acls, i[0], i[1].type.python_type(formwords[i[0]]))
        if not modify:
            db.session.add(acls)
        db.session.commit()
    return adminView()
