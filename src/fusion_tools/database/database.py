"""

Structure schemas for different items in SQLite database

"""
import json
import uuid
import time
import bcrypt

from datetime import datetime

from sqlalchemy import (
    not_, or_, and_, func, select, insert, event, union_all, create_engine, update, exc,
    Column, String, Boolean,ForeignKey, JSON, text)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, 
    mapped_column, Session, scoped_session,
    with_loader_criteria
)
from sqlalchemy.pool import NullPool

from typing import Generator
from contextlib import contextmanager
from shapely.geometry import box, shape

from typing_extensions import Union

from .models import (
    Base, User, UserAccess, 
    VisSession, Item, Layer, 
    LocalItem, RemoteItem,
    Structure, ImageOverlay, Annotation,
    Data
)


TABLE_NAMES = {
    'user': User,
    'user_access': UserAccess,
    'vis_session': VisSession,
    'item': Item,
    'local_item': LocalItem,
    'remote_item': RemoteItem,
    'layer': Layer,
    'structure': Structure,
    'image_overlay': ImageOverlay,
    'annotation': Annotation,
    'data': Data
}


#TODO: add access check to UserAccess table for any query that mentions data from an item
# This includes Item, Layer, Structure, ImageOverlay, and Annotation elements
# either user_id or user_token can be used to identify a user, though user_id is a column in UserAccess


class fusionDB:
    def __init__(self,
                 db_url:str,
                 echo:bool = False):
        
        self.engine = create_engine(
            db_url,
            connect_args={
                "check_same_thread": False
            },
            echo = echo,
            pool_pre_ping = True,
            pool_recycle=3600
        )

        Base.metadata.create_all(bind = self.engine)
        self.SessionLocal = scoped_session(sessionmaker(bind=self.engine))

        """
        # Not sure how to add this as an automatic filterer, this will prevent non-public Items from being available on "select" statements
        @event.listens_for(self.SessionLocal,"do_orm_execute")
        def _do_orm_execute(orm_execute_state):
            if (
                orm_execute_state.is_select
                and not orm_execute_state.is_column_load
                and not orm_execute_state.is_relationship_load
            ):
                orm_execute_state.statement = orm_execute_state.statement.options(
                    with_loader_criteria(entity_or_base = Item, where_criteria = Item.public == True)
                )
        """

    @contextmanager
    def get_db(self) -> Generator[Session, None, None]:
        # Generator type has types, yield, send, return (in this case it yields a Session, sends None and returns None)
        db: Session = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_uuid(self):
        return uuid.uuid4().hex[:24]
    
    def add(self, obj, session = None):
        # Using sessionmaker in a context manager 
        # (closes automatically and rolls back in the event of a database error)
        if session is None:
            with self.get_db() as session:
                session.add(obj)
                session.commit()
        else:
            session.add(obj)

        return True

    def remove(self, obj, session = None):
        # Using sessionmaker in a context manager
        # (closes automatically and rolls back in the event of a database error)
        # Testing if the session object also has a .delete method
        if session is None:
            with self.get_db() as session:
                session.delete(obj)
                session.commit()
        else:
            session.delete(obj)
        
        return True
    
    def get_create(self, table_name:str, inst_id:Union[str,None] = None, kwargs:Union[dict,None] = None):
        """Function for updating or adding items to the database based on whether or not that particular instance already exists

        :param table_name: Name of table that the instance belongs/should belong to
        :type table_name: str
        :param inst_id: A unique id assigned to the new/updated instance, defaults to None
        :type inst_id: Union[str,None], optional
        :param kwargs: Additional arguments used in the creation/updation of an instance, defaults to None
        :type kwargs: Union[dict,None], optional
        :return: Returns the newly created instance if the table name exists 
        """
        with self.get_db() as session:
            if table_name in TABLE_NAMES:
                if not inst_id is None:
                    get_create_result = session.query(
                        TABLE_NAMES.get(table_name)
                    ).filter_by(id = inst_id).first()

                    if not get_create_result:
                        #TODO: Add a "created" option to each model

                        # This is if this thing does not exist in the table
                        updated = datetime.now()
                        get_create_result = TABLE_NAMES.get(table_name)(
                            id = inst_id,
                            **kwargs | {'updated': updated}
                        )

                        self.add(get_create_result, session)
                    else:
                        # This is if this thing DOES exist in the table, update
                        updated = datetime.now()
                        get_create_result = TABLE_NAMES.get(table_name)(
                            id = inst_id,
                            **kwargs | {'updated': updated}
                        )
                        update_kwargs = kwargs | {'updated': updated}
                        session.execute(update(TABLE_NAMES.get(table_name)).where(getattr(TABLE_NAMES.get(table_name),'id')==inst_id).values(update_kwargs))
                
                else:
                    new_id = self.get_uuid()
                    updated = datetime.now()
                    get_create_result = TABLE_NAMES.get(table_name)(
                        id = new_id,
                        **kwargs | {'updated': updated}
                    )

                    self.add(get_create_result, session)

                session.commit()

                return get_create_result
            else:
                return None

    def get_remove(self, table_name:str, inst_id:Union[str,None] = None, user_id: Union[str,None] = None, vis_session_id: Union[str,None] = None):
        """The opposite of self.get_create, checks if an item is present in the table and if it is, deletes it.

        :param table_name: Name of table that the instance belongs to
        :type table_name: str
        :param inst_id: A unique id assigned to the instance, defaults to None
        :type inst_id: Union[str,None], optional
        :return: Returns True if the removal was successful/the table name exists and that instance is in the table
        """
        with self.get_db() as session:
            if table_name in TABLE_NAMES:
                if not inst_id is None:
                    get_remove_result = session.query(
                        TABLE_NAMES.get(table_name)
                    ).filter_by(id = inst_id)

                    if not get_remove_result:
                        #print("Instance not present in db")
                        # If this thing isn't in the table, don't do anything
                        pass
                    else:
                        # This is if this thing DOES exist in the table, remove it
                        if not user_id is None:
                            get_remove_result = get_remove_result.filter(
                                getattr(TABLE_NAMES.get(table_name),'user')==user_id
                            )

                        if not vis_session_id is None:
                            get_remove_result = get_remove_result.filter(
                                getattr(TABLE_NAMES.get(table_name),'session')==vis_session_id
                            )

                        if get_remove_result:
                            for r in get_remove_result.all():
                                self.remove(r,session)
                        else:
                            #print('Not found for this user/vis_session')
                            pass
                else:
                    # Don't delete anything if no instance id is provided
                    get_remove_result = None

                session.commit()

                return get_remove_result
            else:
                return None

    def count(self, table_name:str):
        """Get the count of unique instances within this specific table

        :param table_name: Name of table to query (user, vis_session, item, layer, structure, image_overlay, annotation)
        :type table_name: str
        :return: Count of instances
        :rtype: int
        """

        #TODO: Add some filtering capability here
        with self.get_db() as session:
            if table_name in TABLE_NAMES:
                count_result = session.execute(
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

    async def search(self, search_kwargs:dict, size:Union[int,None] = None, offset = 0, order = None):
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

        if not search_kwargs.get('type','') in TABLE_NAMES:
            return []

        # By default, not validating user access and only searching public items
        public_only_search = True

        #print(f'db search called: {json.dumps(search_kwargs,indent=4)}')
        with self.get_db() as session:
            search_query = session.query(
                TABLE_NAMES.get(search_kwargs.get('type'))
            )
            
            # Applying filters
            search_filters = search_kwargs.get('filters')
            if not search_filters is None:
                table_joins = list(set(list(search_filters.keys())))

                # Determine ahead of time if will need to check user access
                if search_kwargs.get('type')=='item' and 'user' in table_joins:
                    public_only_search = False

                for t in table_joins:
                    if t in TABLE_NAMES:
                        if hasattr(TABLE_NAMES.get(t),'item') and 'user' in table_joins:
                            public_only_search = False

                if search_kwargs.get('type')=='item' and public_only_search:
                    # This covers the case of public-only-searches
                    search_query = search_query.filter(Item.public == True)
                    
                for t in table_joins:
                    if t in TABLE_NAMES:
                        if not t == search_kwargs.get('type'):
                            # Don't join on User, save that for checking public_only_search
                            if t=='user':
                                continue
                            search_query = search_query.join(TABLE_NAMES.get(t))

                        for k,v in search_filters.get(t).items():
                            if type(v)==str:
                                search_query = search_query.filter(
                                    getattr(TABLE_NAMES.get(t),k)==v
                                )
                            elif type(v)==dict:
                                search_query = self.search_op(search_query,t,k,v)

            if not public_only_search:
                # Combining original query with all public items and all items the user has access to
                user_args = search_filters.get('user')
                query_user = self.get_user(
                    user_id = user_args.get('id'),
                    user_token = user_args.get('token')
                )
                if not query_user is None:
                    # Filtering public or has access
                    search_query = search_query.filter(or_(Item.public==True,Item.user_access.any(id = query_user.get('id'))))
                else:
                    # Filtering public
                    search_query = search_query.filter(Item.public==True)

            return_list = []
            for idx,i in enumerate(search_query.all()):
                if not size is None:
                    if len(return_list)==size:
                        break

                if idx>=offset:
                    return_list.append(i.to_dict())

            return return_list
      
    def add_slide(self,
        slide_id:str, 
        slide_name:str, 
        metadata: dict, 
        image_metadata: dict, 
        image_filepath:Union[str,None], 
        annotations_metadata:dict,
        annotations:Union[list,dict,None],
        vis_session_id: Union[str,None] = None,
        user_id: Union[str,None] = None,
        public: bool = False):

        #print(f'{slide_id=}, {public=}')
        new_item = self.get_create(
            table_name = 'local_item',
            inst_id = slide_id,
            kwargs = {
                'name': slide_name,
                'meta': metadata,
                'image_meta': image_metadata,
                'ann_meta': annotations_metadata,
                'filepath': image_filepath,
                'session': vis_session_id,
                'public': public, 
            }
        )

        if not public and user_id is not None:
            self.add_access(slide_id,user_id)

        for ann_idx, ann in enumerate(annotations):
            # Adding layer
            new_layer = self.get_create(
                table_name = 'layer',
                inst_id = ann['properties']['_id'],
                kwargs = {
                    'name': ann['properties']['name'],
                    'item': slide_id,
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
                        'layer': ann['properties']['_id'],
                        'item': slide_id
                    }
                )
            else:
                # Adding Structures in Layer
                for f_idx, f in enumerate(ann['features']):
                    new_structure = self.get_create(
                        table_name = 'structure',
                        inst_id = f['properties'].get('_id',uuid.uuid4().hex[:24]),
                        kwargs = {
                            'geom': f['geometry'],
                            'properties': f['properties'],
                            'layer': ann['properties']['_id'],
                            'item': slide_id,
                        }
                    )

    def add_vis_session(self, vis_session: dict):

        vis_session_kwargs = {
            'user': vis_session.get('user',{}).get('id'),
            'data': vis_session.get('data',{})
        }

        new_vis_session = self.get_create(
            table_name = 'vis_session',
            inst_id = vis_session.get('session',{}).get('id'),
            kwargs = vis_session_kwargs
        )

        new_user = self.get_create(
            table_name = 'user',
            inst_id = vis_session.get('user',{}).get('id'),
            kwargs = {
                k:v
                for k,v in vis_session.get('user',{}).items() 
                if not k=='id'
            }
        )

    def add_access(self, item_id, user_id):

        with self.get_db() as session:
            statement = session.execute(
                insert(UserAccess).values(
                    user_id = user_id,
                    item_id = item_id
                )
            )
        
    def get_user(self, user_token:Union[str,None] = None, user_id: Union[str,None] = None) -> User:

        with self.get_db() as session:
            if not user_token is None:
                search_query = session.execute(
                    select(User).where(User.token==user_token)
                ).first()
            elif not user_id is None:
                search_query = session.execute(
                    select(User).where(User.id==user_id)
                ).first()

            if not search_query is None:
                if len(search_query)>0:
                    return search_query[0].to_dict()
                else:
                    return None
            else:
                return None

    def check_user_login_password(self, user_login: str, user_password: str):

        with self.get_db() as session:
            search_query = session.execute(
                select(User).where(User.login==user_login)
            ).first()

            if not search_query is None:
                if len(search_query)>0:
                    if search_query[0].verify_password(user_password):
                        return search_query[0].to_dict()
                    else:
                        return None
                else:
                    return None
            else:
                return None

    def create_new_user(self, user_kwargs: dict):

        # Required kwargs are login, password, firstname, lastname
        if not all([user_kwargs.get(j) for j in ['login','password','firstName','lastName']]):
            return None
        else:
            # Check uniqueness of login
            with self.get_db() as session:
                search_query = session.execute(
                    select(User).where(User.login==user_kwargs.get('login'))
                ).first()

                if search_query is None:
                    
                    user_kwargs['password'] = bcrypt.hashpw(user_kwargs['password'].encode(),bcrypt.gensalt())
                    user_kwargs['token'] = self.get_uuid()
                    user_kwargs['updated'] = datetime.now()

                    new_id = self.get_uuid()
                    new_user = User(id = new_id, **user_kwargs)
                    user_kwargs['id'] = new_id

                    self.add(new_user, session)
                    session.commit()

                    return user_kwargs
                else:
                    return None

    def check_user_access(self, user_id:str, admin:bool = False) -> list:

        user_access_rows = []
        with self.get_db() as session:
            user_access = session.query(UserAccess)

            for i in user_access.all():
                user_access_rows.append(i)

        # Admins have access to everything
        non_public_access_list = []
        if admin:
            non_public_access_list =  [i[1] for i in user_access_rows]
        else:
            for user,item in user_access_rows:
                if user_id==user:
                    non_public_access_list.append(item)

        return non_public_access_list

    def get_names(self, table_name:str, user_token: Union[str,None] = None, size:Union[int,None]=None, offset = 0):
        
        #TODO: This should get access controlled
        return_names = []
        with self.get_db() as session:

            if table_name in TABLE_NAMES:
                #if not table_name=='item':
                name_query = session.execute(
                    select(getattr(TABLE_NAMES.get(table_name),'name'))
                )
                #else:
                #    name_query = session.query(Item.name)
                #    name_query = name_query.join(UserAccess)

                for a_idx,a in enumerate(name_query.all()):
                    if not size is None:
                        if len(return_names)==size:
                            break
                    if a_idx>=offset:
                        return_names.append(a[0])

            return return_names

    def get_ids(self, table_name: str, user_token: Union[str,None] = None, size:Union[int,None] = None, offset = 0):

        #TODO: This should be access controlled
        return_ids = []
        with self.get_db() as session:

            if table_name in TABLE_NAMES:
                id_query = session.execute(
                    select(getattr(TABLE_NAMES.get(table_name),'id'))
                )

                for a_idx, a in enumerate(id_query.all()):
                    if not size is None:
                        if len(return_ids)==size:
                            break
                    if a_idx>=offset:
                        return_ids.append(a[0])
            
            return return_ids

    async def get_item_annotations(self, item_id:str, user_id:Union[str,None] = None, vis_session_id:Union[str,None] = None)->list:
        """Loading annotations from item database

        :param item_id: String uuid for an item
        :type item_id: str
        :param user_id: String uuid for a user, defaults to None
        :type user_id: Union[str,None], optional
        :param vis_session_id: String uuid for a visualization session, defaults to None
        :type vis_session_id: Union[str,None], optional
        :return: List of GeoJSON-formatted FeatureCollections (and image overlays if present)
        :rtype: list
        """

        item_annotations = []

        item_layers = await self.search(
            search_kwargs = {
                'type': 'layer',
                'filters': {
                    'item': {
                        'id': item_id
                    }
                }
            }
        )

        for l in item_layers:
            layer_name = l.get('name')
            layer_id = l.get('id')

            layer_structures = await self.search(
                search_kwargs={
                    'type': 'structure',
                    'filters': {
                        'layer': {
                            'id': layer_id
                        }
                    }
                }
            )

            if len(layer_structures)>0:
                item_annotations.append(
                    {
                        'type': 'FeatureCollection',
                        'properties': {
                            'name': layer_name,
                            '_id': layer_id
                        },
                        'features': [
                            {
                                'type': 'Feature',
                                'geometry': s.get('geom'),
                                'properties': s.get('properties')
                            }
                            for s in layer_structures
                        ]
                    }
                )
            else:
                # This could be an ImageOverlay layer
                image_overlays = await self.search(
                    search_kwargs = {
                        'type': 'image_overlay',
                        'filters': {
                            'layer': {
                                'id': layer_id
                            }
                        }
                    }
                )

                if len(image_overlays)>0:
                    item_annotations.extend(
                        [
                            i.to_dict() for i in image_overlays
                        ]
                    )

        return item_annotations

    def get_structure_property_keys(self, item_id:Union[str,list,None] = None, layer_id:Union[str,list,None] = None):
        #TODO: Make a more efficient way to get names of properties for each structure
        pass

    def get_structure_property_data(self, item_id:Union[str,list,None] = None, layer_id:Union[str,list,None] = None, structure_id:Union[str,list,None] = None, property_list:Union[str,list] = None):
        """Extracting one or multiple properties from structures given id filters.

        :param item_id: String uuid for one or multiple image items, defaults to None
        :type item_id: Union[str,list,None], optional
        :param layer_id: String uuid for one or multiple layers, defaults to None
        :type layer_id: Union[str,list,None], optional
        :param structure_id: String uuid for one or multiple structures, defaults to None
        :type structure_id: Union[str,list,None], optional
        :param property_list: List of one or more properties to extract from structures, defaults to None
        :type property_list: Union[str,list], optional
        :return: Records-formatted list of dictionaries with each property, along with structure id, bounding box (minx, miny, maxx, maxy), layer id, layer name, item id, and item name
        :rtype: list
        """

        if property_list is None:
            return []
        elif type(property_list)==str:
            property_list = [property_list]

        # Ensuring uniqueness of property names
        property_list = list(set(property_list))

        with self.get_db() as session:
            search_query = session.query(
                *[Structure.properties[p.split(' --> ')] for p in property_list],
                Structure.id,
                Structure.geom,
                Layer.id,
                Layer.name,
                Item.id,
                Item.name
            ).filter(Structure.layer == Layer.id).filter(Layer.item==Item.id)

            if not item_id is None:
                if type(item_id)==list:
                    search_query = search_query.filter(Item.id.in_(item_id))
                elif type(item_id)==str:
                    search_query = search_query.filter(Item.id == item_id)

            if not layer_id is None:
                if type(layer_id)==list:
                    search_query = search_query.filter(Layer.id.in_(layer_id))
                elif type(layer_id)==str:
                    search_query = search_query.filter(Layer.id==layer_id)

            if not structure_id is None:
                if type(structure_id)==list:
                    search_query = search_query.filter(Structure.id.in_(structure_id))
                elif type(structure_id)==str:
                    search_query = search_query.filter(Structure.id==structure_id)
            
            returned_props = property_list + ['structure.id','geometry','layer.id','layer.name','item.id','item.name']
            return_list = []
            for idx,i in enumerate(search_query.all()):
                i_dict = {'_index': idx}
                for prop,prop_name in zip(i,returned_props):
                    if not prop_name=='geometry':
                        i_dict[prop_name] = prop
                    else:
                        i_dict['bbox'] = list(shape(prop).bounds)

                return_list.append(i_dict)

            return return_list

    def get_structures_in_bbox(self, bbox:list, item_id:Union[str,None] = None, layer_id:Union[str,list,None] = None, structure_id:Union[str,list,None] = None):
        """Querying database for structures that intersect with a 

        :param bbox: _description_
        :type bbox: list
        :param item_id: _description_, defaults to None
        :type item_id: Union[str,None], optional
        :param layer_id: _description_, defaults to None
        :type layer_id: Union[str,list,None], optional
        :param structure_id: _description_, defaults to None
        :type structure_id: Union[str,list,None], optional
        :return: _description_
        :rtype: _type_
        """
        
        #TODO: Test the performance of this using shape().intersects() vs. checking min/max ranges for bounding boxes
        with self.get_db() as session:
            start = time.time()
            search_query = session.query(
                Structure.id,
                Structure.geom
            )

            if not item_id is None:
                if type(item_id)==str:
                    search_query = search_query.filter(Item.id == item_id)

            if not layer_id is None:
                if type(layer_id)==list:
                    search_query = search_query.filter(Layer.id.in_(layer_id))
                elif type(layer_id)==str:
                    search_query = search_query.filter(Layer.id==layer_id)

            if not structure_id is None:
                if type(structure_id)==list:
                    search_query = search_query.filter(Structure.id.in_(structure_id))
                elif type(structure_id)==str:
                    search_query = search_query.filter(Structure.id==structure_id)

            # Box should be minx, miny, maxx, maxy
            query_box = box(*bbox)
            return_list = []
            for idx,i in enumerate(search_query.all()):
                structure_id = i[0]
                structure_geom = i[1]
                if shape(structure_geom).intersects(query_box):
                    return_list.append(structure_id)

            return return_list

    def get_structure_generator(self, item_id: Union[str,list,None] = None, layer_id:Union[str,list,None] = None, structure_id: Union[str,list,None] = None):


        with self.get_db() as session:
            search_query = session.query(
                Structure.id,
                Structure.geom,
                Structure.properties
            ).filter(Structure.layer == Layer.id).filter(Layer.item==Item.id)

            if not item_id is None:
                if type(item_id)==list:
                    search_query = search_query.filter(Item.id.in_(item_id))
                elif type(item_id)==str:
                    search_query = search_query.filter(Item.id == item_id)

            if not layer_id is None:
                if type(layer_id)==list:
                    search_query = search_query.filter(Layer.id.in_(layer_id))
                elif type(layer_id)==str:
                    search_query = search_query.filter(Layer.id==layer_id)

            if not structure_id is None:
                if type(structure_id)==list:
                    search_query = search_query.filter(Structure.id.in_(structure_id))
                elif type(structure_id)==str:
                    search_query = search_query.filter(Structure.id==structure_id)
            
            #returned_props = ['structure.id','geometry','structure.properties']
            #return_list = []
            #for idx,i in enumerate(search_query.all()):
            #    i_dict = {'_index': idx}
            #    for prop,prop_name in zip(i,returned_props):
            #        i_dict[prop_name] = prop

            #    return_list.append(i_dict)

            #return return_list
            return search_query.all()

