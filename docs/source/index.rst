.. fusion-tools documentation master file, created by
   sphinx-quickstart on Wed Sep 11 15:22:59 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

*fusion-tools*: Modular creation of dashboards for visualization and analysis of histology data
==========================

.. image:: ../images/slide-annotations-layout.PNG
   :width: 400
   :alt: fusion-tools layout

What is *fusion-tools*?
---------------

*fusion-tools* was designed as a flexible way for users to generate
interactive components which focus on **histological images**. It was 
designed in tandem with *FUSION (Functional Units State Identification in WSIs)*,
which focused on paired analysis of **spatial --omics** data. *fusion-tools* provides
an easy-to-use (hopefully) interface for users to instantiate their own versions of *FUSION*
with incorporation of locally stored data, develop their own interactive components, and 
design their own upload templates for new varieties of spatial data or new cloud-hosted
plugins.  

* *Backend Details*
   *Dash*
   ---------------
   `*Dash* <https://dash.plotly.com/>`_ is a low-code framework for building applications in Python. A minimal example 
   of a *Dash* application include a *layout* featuring various organizational, data storage, and interactive components 
   as well as *callbacks* which codify responses to user interaction with specific components.

   Basic inputs into a *Dash* *callback* include one or more *Input* and *Output* component properties and can also include 
   one or more *State* component properties.

   An example simple *Dash* application is provided below (curtesy of `the *Dash* website <https://dash.plotly.com/minimal-app>`_):
   
   .. code-block:: python

      # Package imports:
      from dash import Dash, html, dcc, callback, Output, Input
      import plotly.express as px
      import pandas as pandas

      # Reading in data for application
      df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv')

      # Initializing Dash application
      app = Dash()

      # Defining layout for the application
      app.layout = [
         html.H1(
            children = "Title of Dash App",
            style = {'textAlign': 'center'}
         ),
         dcc.Dropdown(
            options = df.country.unique(),
            value = 'Canada',
            id = 'dropdown-selection'
         ),
         dcc.Graph(
            id = 'graph-content'
         )
      ]

      # Defining callback (dropdown selection->update figure displayed in graph)
      @callback(
         Output('graph-content','figure'),
         Input('dropdown-selection','value')
      )
      def update_graph(value):
         dff = df[df.country==value]
         return px.line(dff, x = 'year', y = 'pop')
      

      if __name__=='__main__':
         # Starting the default application server
         app.run(debug=True)


   *fusion-tools* components are written as `*DashBlueprint*<https://www.dash-extensions.com/sections/enrich>`_ 
   objects. Similar to `Flask Blueprints<https://flask.palletsprojects.com/en/stable/blueprints/>`_, 
   *DashBlueprint*s enable piecewise construction of full applications by embedding functional components into 
   a single unified layout. 

   An example *Tool* is shown below with the same functionality as the minimal *Dash* application above:

   .. code-block:: python

      from dash import dcc
      from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
      from fusion_tools.components import Tool
      import pandas as pd
      import plotly.express as px

      class BasicTool(Tool):
         def __init__(self):

            super().__init__()

            self.df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv')


         def __str__(self):
            return 'Basic Tool'

         def load(self, component_prefix:int):

            self.component_prefix = component_prefix

            self.title = 'Basic Tool'
            self.blueprint = DashBlueprint(
               transforms = [
                  PrefixIdTransform(prefix = f'{component_prefix}'),
                  MultiplexerTransform()
               ]
            )

            self.get_callbacks()
         
         def gen_layout(self, session_data:dict):

            layout = html.Div([
               html.H1(
                  children = "Title of Dash App",
                  style = {'textAlign': 'center'}
               ),
               dcc.Dropdown(
                  options = self.df.country.unique(),
                  value = 'Canada',
                  id = 'dropdown-selection'
               ),
               dcc.Graph(
                  id = 'graph-content'
               )
            ])

            return layout

         def get_callbacks(self):

            self.blueprint.callback(
               [
                  Input('dropdown-selection','value')
               ],
               [
                  Output('graph-content')
               ]
            )(self.update_graph)

         def update_graph(self, new_country):

            country_data = self.df[self.df.country==new_country]
            new_plot = px.line(country_data, x = 'year', y = 'pop')


   This can then be added into a *fusion-tools* *Visualization* as below:

   .. code-block:: python

      from fusion_tools import Visualization
      from basictool import BasicTool

      new_vis = Visualization(
         components = [
            BasicTool()
         ]
      )

      new_vis.start()

   *Digital Slide Archive (DSA)*
   ---------------
   `*Digital Slide Archive (DSA)*<https://github.com/DigitalSlideArchive/digital_slide_archive>`_ is an open-source 
   resource for organization of large whole slide images (WSIs) as well as providing an interface (`*HistomicsUI*<https://github.com/DigitalSlideArchive/HistomicsUI>`_)
   for image annotation and running computational analyses. It provides a RESTful API which enables programmatic 
   access of data that is stored on a given *DSA* instance as well as handling POST, GET, PUT, etc. requests.

   *fusion-tools* provides several components which integrate with a running *DSA* instance to provide alternative 
   interfaces for visualizing data, stored within image annotations, in conjunction with Histology images. Furthermore,
   *fusion-tools* provides a format for defining upload templates (*UploadType*s) that allow adminstrators to pre-specify 
   files, metadata, and processing steps used for a specific type of data. While it does not implement every possible process 
   that is implemented in *DSA* (for example, copying/moving items, modifying user details, and several others), *fusion-tools* 
   may be a valuable resource for developers that use *DSA* to design custom visualization and interaction pages (in Python) 
   to share with collaborators as well as integrating plugins with specific sets of inputs to user-interactions.


Table of contents
---------------

.. toctree::
   :maxdepth: 6
   :caption: Contents:

   modules