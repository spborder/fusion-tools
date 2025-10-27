"""
Defining models for fusionDB
"""
import enum
from typing import List
from sqlalchemy import (
    Table, Column, String, 
    Boolean, Integer, ForeignKey, 
    JSON, DateTime, Enum
)
from sqlalchemy.orm import (
    declarative_base, mapped_column, relationship,
    Mapped    
)
import bcrypt

from shapely.geometry import box

#TODO: Current access control rules specify that if an item is not public then everything associated with that item is also not public
# Likewise, if a user has access to an item, they will have access to everything on that item.

Base = declarative_base()

# Which users can access which items
UserAccess = Table(
    'user_access',
    Base.metadata,
    Column('user_id',String,ForeignKey('user.id',ondelete='CASCADE')),
    Column('item_id',String,ForeignKey('item.id',ondelete='CASCADE'))
)

class User(Base):
    __tablename__ = 'user'
    id = mapped_column(String(24), primary_key = True)
    login = Column(String,unique=True)
    password = Column(String(60))

    firstName = Column(String)
    lastName = Column(String)
    email = Column(String)

    admin = Column(Boolean)
    updated = Column(DateTime)

    token = Column(String)

    item_access: Mapped[List["Item"]] = relationship(
        secondary = UserAccess, back_populates="user_access"
    )

    external = Column(JSON)

    meta = Column(JSON)

    def verify_password(self, query_pword) -> bool:
        return bcrypt.checkpw(
            query_pword.encode(), self.password
        )

    def to_dict(self):
        user_dict = {
            'id': self.id,
            'login': self.login,
            'firstName': self.firstName,
            'lastName': self.lastName,
            'email': self.email,
            'meta': self.meta,
            'external': self.external,
            'admin': self.admin,
            'updated': self.updated,
            'token': self.token
        }

        return user_dict
    


class VisSession(Base):
    __tablename__='vis_session'
    id = mapped_column(String(24),primary_key = True)
    # Can multiple users access the same vis session?
    user = mapped_column(ForeignKey("user.id"))

    name = Column(String)

    #TODO: Add "current" section for current items in vis_session

    # Visualization session data stored as JSON
    data = Column(JSON)
    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        vis_dict = {
            'id': self.id,
            'user': self.user,
            'data': self.data,
            'meta': self.meta,
            'updated': self.updated
        }

        return vis_dict

class ItemType(enum.Enum):
    local = 1
    remote = 2


class Item(Base):
    __tablename__='item'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    meta = Column(JSON)
    image_meta = Column(JSON)
    ann_meta = Column(JSON)

    session = mapped_column(ForeignKey("vis_session.id"))
    updated = Column(DateTime)

    public = Column(Boolean)

    user_access: Mapped[List["User"]] = relationship(
        secondary = UserAccess, back_populates="item_access"
    )
    type = Column(Enum(ItemType))

    __mapper_args__ = {
        'polymorphic_identity': 'item',
        'polymorphic_on': 'type'
    }

    def to_dict(self):
        item_dict = {
            'id': self.id,
            'name': self.name,
            'meta': self.meta,
            'image_meta': self.image_meta,
            'ann_meta': self.ann_meta,
            'session': self.session,
            'updated': self.updated,
            'public': self.public
        }

        return item_dict

class LocalItem(Item):
    __tablename__ = 'local_item'
    id = mapped_column(ForeignKey('item.id'),primary_key = True)

    url = Column(String)
    filepath = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': 'local_item'
    }

    def to_dict(self):

        item_dict = super().to_dict() | {'filepath': self.filepath, 'url': self.url, 'type': self.type}

        return item_dict

class RemoteItem(Item):
    __tablename__ = 'remote_item'
    id = mapped_column(ForeignKey('item.id'),primary_key = True)

    url = Column(String)
    remote_id = Column(String(24))

    __mapper_args__ = {
        'polymorphic_identity': 'remote_item'
    }

    def to_dict(self):

        item_dict = super().to_dict() | {'url': self.url, 'remote_id': self.remote_id, 'type': self.type}

        return item_dict

class Layer(Base):
    __tablename__ = 'layer'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    item = mapped_column(ForeignKey("item.id"))

    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        layer_dict = {
            'id': self.id,
            'name': self.name,
            'item': self.item,
            'meta': self.meta,
            'updated': self.updated
        }

        return layer_dict

class Structure(Base):
    __tablename__ = 'structure'
    id = mapped_column(String(24),primary_key = True)
    geom = Column(JSON)

    properties = Column(JSON)

    layer = mapped_column(ForeignKey('layer.id'))
    item = mapped_column(ForeignKey('item.id'))
    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        structure_dict = {
            'id': self.id,
            'geom': self.geom,
            'properties': self.properties,
            'layer': self.layer,
            'meta': self.meta,
            'updated': self.updated
        }

        return structure_dict
    
    def to_geojson(self):
        geojson_dict = {
            'type': 'Feature',
            'geometry': self.geom,
            'properties': self.properties
        }

        return geojson_dict

class ImageOverlay(Base):
    __tablename__ = 'image_overlay'
    id = mapped_column(String(24),primary_key = True)
    bounds = Column(JSON)

    properties = Column(JSON)
    image_src = Column(String)

    layer = mapped_column(ForeignKey('layer.id'))
    item = mapped_column(ForeignKey('item.id'))
    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        img_overlay_dict = {
            'id': self.id,
            'bounds': self.bounds,
            'properties': self.properties,
            'image_src': self.image_src,
            'layer': self.layer,
            'meta': self.meta,
            'updated': self.updated
        }

        return img_overlay_dict
    
    def to_geojson(self):
        img_overlay_geojson = {
            'type': 'Feature',
            'geometry': list(box(*self.bounds).exterior.coords),
            'properties': self.properties
        }

        return img_overlay_geojson

class Annotation(Base):
    __tablename__ = 'annotation'
    id = Column(String(24),primary_key = True)

    user = mapped_column(ForeignKey('user.id'))
    session = mapped_column(ForeignKey('vis_session.id'))
    item = mapped_column(ForeignKey('item.id'))
    layer = mapped_column(ForeignKey('layer.id'))
    structure = mapped_column(ForeignKey('structure.id'))

    # Storing all annotation data as JSON
    data = Column(JSON)
    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        ann_dict = {
            'id': self.id,
            'user': self.user,
            'session': self.session,
            'item': self.item,
            'layer': self.layer,
            'structure': self.structure,
            'data': self.data,
            'meta': self.meta,
            'updated': self.updated
        }

        return ann_dict

class Data(Base):
    __tablename__ = 'data'
    id = Column(String(24),primary_key = True)

    user = mapped_column(ForeignKey('user.id'))
    session = mapped_column(ForeignKey('vis_session.id'))
    item = mapped_column(ForeignKey('item.id'))
    layer = mapped_column(ForeignKey('layer.id'))
    structure = mapped_column(ForeignKey('structure.id'))

    # filepath to query-able filetype
    filepath = Column(String)
    updated = Column(DateTime)

    meta = Column(JSON)

    def to_dict(self):
        data_dict = {
            'id': self.id,
            'user': self.user,
            'session': self.session,
            'item': self.item,
            'layer': self.item,
            'structure': self.structure,
            'filepath': self.filepath,
            'meta': self.meta,
            'updated': self.updated
        }

        return data_dict

# LocalData & RemoteData?
# Same deal as with LocalItem & RemoteItem

