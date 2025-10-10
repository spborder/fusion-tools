"""Testing pymongo and mongo-engine
"""

import os
import sys
sys.path.append('./src/')

import uuid
import json
from tqdm import tqdm

from fusion_tools.handler.dsa_handler import DSAHandler

#from __future__ import annotations
from typing import List
from sqlalchemy import func, distinct, select, create_engine, text, MetaData, Table, Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column, relationship, backref
from sqlalchemy.types import Unicode

import numpy as np

# This should work if spatialite is installed but installation is OS-dependent
#from geoalchemy2 import Geometry

#sys.path.append('C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\FUSION_env\\Spatialite\\mod_spatialite-5.1.0-win-x86\\')
#os.chdir('C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\FUSION_env\\Spatialite\\mod_spatialite-5.1.0-win-x86\\')
#os.environ["SPATIALITE_LIBRARY_PATH"] = 'mod_spatialite.dll'

#print(os.environ.get('SPATIALITE_LIBRARY_PATH'))

from shapely.geometry import shape

import geopandas as gpd
import time

Base = declarative_base()

class User(Base):
    __tablename__ = 'user'
    id = mapped_column(String(24), primary_key = True)

class VisSession(Base):
    __tablename__='vis_session'
    id = mapped_column(String(24),primary_key = True)
    user = mapped_column(ForeignKey("user.id"))

class Item(Base):
    __tablename__='item'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    meta = Column(JSON)
    image_meta = Column(JSON)

    session = mapped_column(ForeignKey("visSession.id"))

class Layer(Base):
    __tablename__ = 'layer'
    id = mapped_column(String(24),primary_key = True)
    name = Column(String)
    item = mapped_column(ForeignKey("item.id"))

class Structure(Base):
    __tablename__ = 'structure'
    id = mapped_column(String(24),primary_key = True)
    #geom = Column(Geometry('POLYGON'))
    geom = Column(JSON)

    properties = Column(JSON)

    layer = mapped_column(ForeignKey('layer.id'))
    item = mapped_column(ForeignKey('item.id'))
    """
    intras = relationship(
        'IntraStructure',
        primaryjoin = 'func.ST_Contains(foreign(Structure.geom),IntraStructure.geom).as_comparison(1,2)',
        backref = backref('structure',uselist=False),
        viewonly=True,
        uselist=True
    )
    """

class IntraStructure(Base):
    __tablename__ = 'intrastructure'

    id = mapped_column(String(24),primary_key = True)
    name = mapped_column(String)
    #geom = Column(Geometry)
    geom = Column(JSON)

    properties = mapped_column(String)


class dbObject:
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        echo=False,
        #plugins=["geoalchemy2"]
    )

    print(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind = engine)


def main():
    
    # Create an in-memory-only SQLite database
    # URL string indicates that database is sqlite, using the Python DBAPI, and DB is located in memory

    example_anns_path = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\FFPE Niche Mappings\\Full Annotations\\'
    
    """
    Tables:
        - VisSession
            - User
            - Item
                - Layer
                    - Structure
                        - IntraStructure

    """
    # Defining the session object 
    #ex_session_obj = Session()    
    # Defining example user
    user_id = uuid.uuid4().hex[:24]
    ex_user = User(
        id = user_id
    )

    # Adding to session
    with dbObject.Session() as session:
        session.add(
            ex_user
        )
        session.commit()


    # Defining example visualization session
    ex_vis_id = uuid.uuid4().hex[:24]
    ex_vis_sess = VisSession(
        id = ex_vis_id,
        user = user_id
    )

    # Adding to session
    with dbObject.Session() as session:
        session.add(
            ex_vis_sess
        )
        session.commit()

    for ex_idx,ex in tqdm(enumerate(os.listdir(example_anns_path)),total = len(os.listdir(example_anns_path))):

        anns_path = os.path.join(example_anns_path,ex)
        with open(anns_path,'r') as f:
            example_anns = json.load(f)
            f.close()

        # Defining example item
        ex_item_id = uuid.uuid4().hex[:24]
        ex_item = Item(
            id = ex_item_id,
            name = ex,
            meta = {
                'item_idx': ex_idx,
            },
            image_meta = {
                'image': 'metadata',
                'random_list': [np.random.randint(low=0,high=10) for i in range(np.random.randint(low=0,high=5))],
                'random_int': np.random.randint(low=0,high=100)
            },
            session = ex_vis_id
        )

        # Adding to session
        with dbObject.Session() as session:
            session.add(
                ex_item
            )
            session.commit()

        # Defining example layers
        for a in example_anns:
            ex_layer_id = a['properties']['_id']
            ex_layer = Layer(
                id = ex_layer_id,
                name = a['properties']['name'],
                item = ex_item_id
            )

            with dbObject.Session() as session:
                session.add(
                    ex_layer
                )
                session.commit()

            structure_objs = []
            for f in a['features']:
                ex_structure = Structure(
                    id = f['properties']['_id'],
                    #geom = shape(f['geometry']),
                    geom = f['geometry'],
                    properties = f['properties'],
                    layer = ex_layer_id,
                    item = ex_item_id
                )
                structure_objs.append(ex_structure)

            with dbObject.Session() as session:

                session.add_all(structure_objs)
                session.commit()

    # Executing query of structures with specific property
    # By default, JSON-type columns are parsed using json.loads, nested keys are accessed sequentially in a list
    with dbObject.Session() as session:
        result = session.execute(
            select(func.avg(Structure.properties["Main_Cell_Types","POD"].as_float()))
            .join(Layer)
            .where(Layer.name.in_(['Glomeruli','Sclerotic Glomeruli']))
            .where(Structure.properties["Main_Cell_Types","POD"].as_float() > 0.5)
        )
        for a in result.all():
            print(a)

    with dbObject.Session() as session:
        result = session.execute(
            select(Item.name)
        )
        item_names = []
        for a in result.all():
            item_names.append(a[0])

    # Use a .join to access properties from different tables
    
    search_dict = {
        'layer.name': 'Glomeruli'
    }
    for idx,i in enumerate(item_names):
        with dbObject.Session() as session:
            count_query = session.query(Structure)

            search_dict['item.name'] = i
            if any(['layer' in i for i in list(search_dict.keys())]):
                count_query = count_query.join(Layer)

            if any(['item' in i for i in list(search_dict.keys())]):
                count_query = count_query.join(Item)

            for k,v in search_dict.items():
                if 'item' in k:
                    count_query = count_query.filter(getattr(Item,k.split('.')[-1])==v)
                elif 'layer' in k:
                    count_query = count_query.filter(
                        getattr(Layer,k.split('.')[-1])==v
                    )
            
            count = 0
            for a in count_query.all():
                count+=1

            print(f'Item: {i} has: {count} Glomeruli')




if __name__=='__main__':
    main()


