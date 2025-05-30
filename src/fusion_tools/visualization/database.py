"""

Structure schemas for different items in SQLite database

"""

import uuid

from sqlalchemy import (
    not_, func, select, create_engine,
    Column, String, Boolean,ForeignKey, JSON)
from sqlalchemy.orm import declarative_base, sessionmaker,mapped_column

from shapely.geometry import box

from typing_extensions import Union

from fusion_tools.tileserver import Slide

Base = declarative_base()

class User(Base):
    __tablename__ = 'user'
    id = mapped_column(String(24), primary_key = True)
    login = Column(String)

    firstName = Column(String)
    lastName = Column(String)
    email = Column(String)

    admin = Column(Boolean)

    def to_dict(self):
        user_dict = {
            'id': self.id,
            'login': self.login,
            'firstName': self.firstName,
            'lastName': self.lastName,
            'email': self.email,
            'admin': self.admin
        }

        return user_dict
    
class VisSession(Base):
    __tablename__='visSession'
    id = mapped_column(String(24),primary_key = True)
    # Can multiple users access the same vis session?
    user = mapped_column(ForeignKey("user.id"))

    def to_dict(self):
        vis_dict = {
            'id': self.id,
            'user': self.user
        }

        return vis_dict

class Item(Base):
    __tablename__='item'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    meta = Column(JSON)
    image_meta = Column(JSON)
    ann_meta = Column(JSON)

    file_path = Column(String)

    session = mapped_column(ForeignKey("visSession.id"))

    def to_dict(self):
        item_dict = {
            'id': self.id,
            'name': self.name,
            'meta': self.meta,
            'image_meta': self.image_meta,
            'session': self.session
        }

        return item_dict

class Layer(Base):
    __tablename__ = 'layer'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    item = mapped_column(ForeignKey("item.id"))

    def to_dict(self):
        layer_dict = {
            'id': self.id,
            'name': self.name,
            'item': self.item
        }

        return layer_dict

class Structure(Base):
    __tablename__ = 'structure'
    id = mapped_column(String(24),primary_key = True)
    geom = Column(JSON)

    properties = Column(JSON)

    layer = mapped_column(ForeignKey('layer.id'))
    item = mapped_column(ForeignKey('item.id'))

    def to_dict(self):
        structure_dict = {
            'id': self.id,
            'geom': self.geom,
            'properties': self.properties,
            'layer': self.layer
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

    def to_dict(self):
        img_overlay_dict = {
            'id': self.id,
            'bounds': self.bounds,
            'properties': self.properties,
            'image_src': self.image_src,
            'layer': self.layer
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
    session = mapped_column(ForeignKey('visSession.id'))
    item = mapped_column(ForeignKey('item.id'))
    layer = mapped_column(ForeignKey('layer.id'))
    structure = mapped_column(ForeignKey('structure.id'))

    classifications = Column(JSON)
    segmentations = Column(JSON)

    def to_dict(self):
        ann_dict = {
            'id': self.id,
            'user': self.user,
            'session': self.session,
            'item': self.item,
            'layer': self.layer,
            'structure': self.structure,
            'classifications': self.classifications,
            'segmentations': self.segmentations
        }

        return ann_dict


TABLE_NAMES = {
    'user': User,
    'visSession': VisSession,
    'item': Item,
    'layer': Layer,
    'structure': Structure,
    'image_overlay': ImageOverlay,
    'annotation': Annotation
}

class fusionDB:
    def __init__(self,
                 db_url: str,
                 echo: bool = False):
        
        self.engine = create_engine(
            db_url,
            echo = echo
        )

        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)

        self.session = Session()
        self.tables = Base.metadata.tables.keys()

    def get_uuid(self):

        return uuid.uuid4().hex[:24]
    
    def add(self, obj):
        
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)

        return True

    def get_create(self, table_name:str, inst_id:Union[str,None] = None, kwargs:Union[dict,None] = None):
        
        if table_name in TABLE_NAMES:
            if not inst_id is None:
                get_create_result = self.session.query(
                    TABLE_NAMES.get(table_name)
                ).filter_by(id = inst_id).first()
            
            else:
                new_id = self.get_uuid()
                get_create_result = TABLE_NAMES.get(table_name)(
                    id = new_id,
                    **kwargs
                )

                self.add(get_create_result)

            return get_create_result
        else:
            return None

    def count(self, table_name:str):
        """Get the count of unique instances within this specific table

        :param table_name: Name of table to query (user, visSession, item, layer, structure, image_overlay, annotation)
        :type table_name: str
        :return: Count of instances
        :rtype: int
        """
        #TODO: Add some filtering capability here
        if table_name in TABLE_NAMES:
            count_result = self.session.execute(
                select(func.count(func.distinct(TABLE_NAMES.get(table_name).id)))
            ).one()

            return count_result[0]
        else:
            return 0

    def search_op(self, search_query, table_name:str, column:str, op:dict):
        """Method for applying different types of filters to database queries

        :param search_query: DB query object
        :type search_query: None
        :param table_name: Name of table being searched
        :type table_name: str
        :param column: Name of column being queried
        :type column: str
        :param op: Operation dictionary
        :type op: dict
        :return: Updated DB query object
        :rtype: None
        """
        op_type = list(op.keys())[0]
        op_query = list(op.values())
        if op_type in ['==','!=','>','<','>=','<=','in','!in']:
            # Numeric operations
            if all([type(i) in [int,float] for i in op_query]) and op_type in ['==','!=','>','<','>=','<=']:
                if op_type=='==':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column)==op_query[0]
                    )
                elif op_type=='!=':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column)!=op_query[0]
                    )
                elif op_type=='>':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) > op_query[0]
                    )
                elif op_type=='>=':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) >= op_query[0]
                    )
                elif op_type=='<':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) < op_query[0]
                    )
                elif op_type=='<=':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) <= op_query[0]
                    )

            # String operations
            elif all([type(i)==str for i in op_query]) and op_type in ['==','!=']:
                if op_type=='==':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) == op_query[0]
                    )
                elif op_type=='!=':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column) != op_query[0]
                    )
            
            # List operations
            elif all([type(i)==list for i in op_query]) and op_type in ['in','!in']:
                if op_type=='in':
                    search_query = search_query.filter(
                        getattr(TABLE_NAMES.get(table_name),column).in_(op_query[0])
                    )
                elif op_type=='!in':
                    search_query = search_query.filter(
                        not_(getattr(TABLE_NAMES.get(table_name),column).in_(op_query[0]))
                    )

            return search_query

        else:
            return search_query

    def search(self, search_kwargs:dict, size:Union[int,None] = None, offset = 0, order = None):
        """Search DB

        :param search_kwargs: Dictionary containing "type" (table name) and "filters"
        :type search_kwargs: dict
        :param size: Number of instances to return, if None returns all that match the search, defaults to None
        :type size: int, optional
        :param offset: Offset of instances to return from search, defaults to 0
        :type offset: int, optional
        :param order: Name of column to order by (Not Implemented), defaults to None
        :type order: None, optional
        :return: Results of DB search
        :rtype: list
        """
        if search_kwargs.get('type','') in TABLE_NAMES:
            search_query = self.session.query(
                TABLE_NAMES.get(search_kwargs.get('type'))
            )
            
            # Applying filters
            search_filters = search_kwargs.get('filters')
            if not search_filters is None:
                
                table_joins = list(set(list(search_filters.keys())))
                for t in table_joins:
                    if t in TABLE_NAMES:
                        search_query = search_query.join(TABLE_NAMES.get(t))

                        for k,v in search_filters.get(t):
                            if type(v)==str:
                                search_query = search_query.filter(
                                    getattr(TABLE_NAMES.get(t),k)==v
                                )
                            elif type(v)==dict:
                                search_query = self.search_op(search_query,t,k,v)


            return_list = []
            for idx,i in enumerate(search_query.all()):
                if not size is None:
                    if len(return_list)==size:
                        break

                if idx>=offset:
                    return_list.append(i.to_dict())
            
            return return_list

        else:
            return []
        
    def add_slide(self, slide_id:str, slide_name:str, slide:Slide):

        new_item = self.get_create(
            table_name = 'item',
            inst_id = slide_id,
            kwargs = {
                'name': slide_name,
                'meta': slide.metadata,
                'image_meta': slide.image_metadata,
                'ann_meta': slide.annotations_metadata,
                'file_path': slide.image_filepath
            }
        )

        for ann_idx, ann in slide.processed_annotations:
            # Adding layer
            new_layer = self.get_create(
                table_name = 'layer',
                inst_id = ann['properties']['_id'],
                kwargs = {
                    'name': ann['properties']['name'],
                    'item': slide_id
                }
            )

            if 'image_path' in ann:
                # Adding image overlay layer
                new_image_overlay = self.get_create(
                    table_name = 'image_overlay',
                    inst_id = ann['properties']['_id'],
                    kwargs = {
                        'bounds': ann['image_bounds'],
                        'properties': ann['image_properties'],
                        'image_src': ann['image_path'],
                        'layer': ann['properties']['_id']
                    }
                )
            else:
                # Adding Structures in Layer
                for f_idx, f in enumerate(ann['features']):
                    new_structure = self.get_create(
                        table_name = 'structure',
                        inst_id = f['properties']['_id'],
                        kwargs = {
                            'geom': f['geometry'],
                            'properties': f['properties'],
                            'layer': ann['properties']['_id'],
                            'item': slide_id
                        }
                    )

    def get_names(self, table_name:str, size:Union[int,None]=None, offset = 0):

        return_names = []
        if table_name in TABLE_NAMES:
            name_query = self.session.execute(
                select(getattr(TABLE_NAMES.get(table_name),'name'))
            )

            for a_idx,a in enumerate(name_query.all()):
                if not size is None:
                    if len(return_names)==size:
                        break
                if a_idx>=offset:
                    return_names.append(a[0])

        return return_names
            



