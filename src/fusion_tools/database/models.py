"""
Defining models for fusionDB
"""
from typing import List
from sqlalchemy import (
    Table, Column, String, Boolean, Integer, ForeignKey, JSON, DateTime)
from sqlalchemy.orm import (
    declarative_base, mapped_column, relationship,
    Mapped    
)

from shapely.geometry import box

#TODO: Current access control rules specify that if an item is not public then everything associated with that item is also not public
# Likewise, if a user has access to an item, they will have access to everything on that item.

Base = declarative_base()


UserAccess = Table(
    'user_access',
    Base.metadata,
    Column('user_id',String,ForeignKey('user.id',ondelete='CASCADE')),
    Column('item_id',String,ForeignKey('item.id',ondelete='CASCADE'))
)

class User(Base):
    __tablename__ = 'user'
    id = mapped_column(String(24), primary_key = True)
    login = Column(String)

    firstName = Column(String)
    lastName = Column(String)
    email = Column(String)

    admin = Column(Boolean)
    updated = Column(DateTime)

    token = Column(String)

    item_access: Mapped[List["Item"]] = relationship(
        secondary = UserAccess, back_populates="user_access"
    )


    def to_dict(self):
        user_dict = {
            'id': self.id,
            'login': self.login,
            'firstName': self.firstName,
            'lastName': self.lastName,
            'email': self.email,
            'admin': self.admin,
            'updated': self.updated,
            'token': self.token
        }

        return user_dict
    


"""
class UserAccess(Base):
    __tablename__ = 'user_access'

    id = Column(String(24), primary_key = True)

    user = mapped_column(ForeignKey("user.id"))
    item = mapped_column(ForeignKey("item.id"))

    #TODO: placeholder column, public items aren't added here.
    permission = Column(Integer)

    updated = Column(DateTime)

    def to_dict(self):
        user_access_dict = {
            'id': self.id,
            'user': self.user,
            'item': self.item
        }
        return user_access_dict
"""

class VisSession(Base):
    __tablename__='vis_session'
    id = mapped_column(String(24),primary_key = True)
    # Can multiple users access the same vis session?
    user = mapped_column(ForeignKey("user.id"))

    #TODO: Add "current" section for current items in vis_session

    # Visualization session data stored as JSON
    data = Column(JSON)
    updated = Column(DateTime)

    def to_dict(self):
        vis_dict = {
            'id': self.id,
            'user': self.user,
            'data': self.data,
            'updated': self.updated
        }

        return vis_dict

class Item(Base):
    __tablename__='item'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    meta = Column(JSON)
    image_meta = Column(JSON)
    ann_meta = Column(JSON)

    filepath = Column(String)

    session = mapped_column(ForeignKey("vis_session.id"))
    updated = Column(DateTime)

    public = Column(Boolean)

    user_access: Mapped[List["User"]] = relationship(
        secondary = UserAccess, back_populates="item_access"
    )

    def to_dict(self):
        item_dict = {
            'id': self.id,
            'name': self.name,
            'meta': self.meta,
            'image_meta': self.image_meta,
            'ann_meta': self.ann_meta,
            'filepath': self.filepath,
            'session': self.session,
            'updated': self.updated,
            'public': self.public
        }

        return item_dict

class Layer(Base):
    __tablename__ = 'layer'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    item = mapped_column(ForeignKey("item.id"))

    updated = Column(DateTime)

    def to_dict(self):
        layer_dict = {
            'id': self.id,
            'name': self.name,
            'item': self.item,
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

    def to_dict(self):
        structure_dict = {
            'id': self.id,
            'geom': self.geom,
            'properties': self.properties,
            'layer': self.layer,
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

    def to_dict(self):
        img_overlay_dict = {
            'id': self.id,
            'bounds': self.bounds,
            'properties': self.properties,
            'image_src': self.image_src,
            'layer': self.layer,
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

    def to_dict(self):
        ann_dict = {
            'id': self.id,
            'user': self.user,
            'session': self.session,
            'item': self.item,
            'layer': self.layer,
            'structure': self.structure,
            'data': self.data,
            'updated': self.updated
        }

        return ann_dict

#TODO: Create table "Data" with accessibility of tabular, -Data (AnnData, MuData, SpatialData) objects, arrays, etc.








