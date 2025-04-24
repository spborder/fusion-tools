Introduction to Dash
======================

*Dash*
---------------
`Dash <https://dash.plotly.com/>`_ is a low-code framework for building applications in Python. A minimal example 
of a *Dash* application include a *layout* featuring various organizational, data storage, and interactive components 
as well as *callbacks* which codify responses to user interaction with specific components.

Basic inputs into a *Dash* *callback* include one or more *Input* and *Output* component properties and can also include 
one or more *State* component properties.

An example simple *Dash* application is provided below (curtesy of `the Dash website <https://dash.plotly.com/minimal-app>`_):

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


*fusion-tools* components are written as `DashBlueprint <https://www.dash-extensions.com/sections/enrich>`_ 
objects. Similar to `Flask Blueprints <https://flask.palletsprojects.com/en/stable/blueprints/>`_, 
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

*Pattern-matching callbacks*

`Pattern-matching callbacks <https://dash.plotly.com/pattern-matching-callbacks>` is a method in *Dash* to apply callbacks to either multiple 
components of the same "type" but different "index" or to associate callbacks with other 
components with the same "index".

For example, all components that you want to associate with a callback are given an "id" 
property. The "id" can consist of either a *str* (e.g.: "component-1") or a dictionary 
with keys: "type" and "index" as below:

.. code-block:: python

    example_div = html.Div(
        id = 'example-str-component',
        children = [
            "This component is defined just with a string id"
        ]
    )
    example_div2 = html.Div(
        id = {'type': 'example-pattern-matching-component', 'index': 0},
        children = [
            "This is a component of the type: 'example-pattern-matching-component' with the index 0"
        ]
    )
    example_div3 = html.Div(
        id = {'type': 'example-pattern-matching-component', 'index': 1},
        children = [
            "This is a component of the type: 'example-pattern-matching-component' with the index 0"
        ]
    )

This lets you write one callback that can impact different components as below:

.. code-block:: python

    @callback(
        [
            Output({'type': 'example-pattern-matching-component','index': ALL}, 'children')
        ],
        [
            Input({'type': 'some-random-button','index': ALL},'n_clicks')
        ]
    )
    def update_multiple_components(clicks):

        # This callback responds to a button click and returns the same string 
        # to each output div.
        output_str = 'This component has been updated!'

        # dash.ctx.outputs_list can tell you ahead of time how many pattern-matching components 
        # should be updated with each output.

        return [output_str] * len(ctx.outputs_list[0])

    @callback(
        [
            Output({'type': 'example-pattern-matching-component','index': MATCH}, 'children')
        ],
        [
            Input({'type': 'some-random-dropdown','index': MATCH},'value')
        ]
    )
    def update_matching_component(dropdown_value):

        # In this scenario, a different dropdown menu is present for each "index" (or at least the ones 
        # that are currently in the layout). Selecting a value from each dropdown impacts only 
        # the Div with the same index.
        # NOTE: If the same components are used as "Output"s in multiple callbacks, you need to use 
        # the MultiPlexerTransform() (https://www.dash-extensions.com/transforms/multiplexer_transform)

        return f'Dropdown of index: {ctx.triggered_id["index"]} has value: {dropdown_value}'

Notice how the outputs for *ALL* pattern-matching callbacks are "lists" while outputs for *Match* pattern-matching 
callbacks can be a single output. Even if there is only output id that matches the *Output* any pattern-matching 
callbacks that contain *ALL* have to be a sequence.

Another use-case for pattern-matching callbacks is that it allows you to define callbacks for components 
which are not in the current app layout. This is useful for *DashBlueprint* objects as the blueprint layout 
may not be active at all times. NOTE: This is a somewhat irregular application of multi-page applications in 
Dash. For more information on multi-page applications see `this link <https://dash.plotly.com/urls>`.






