Introduction to Dash
======================

*Dash*
--------
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


A `BasicTool` in `fusion-tools`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

*fusion-tools* components are written as `DashBlueprint <https://www.dash-extensions.com/sections/enrich>`_ 
objects. Similar to `Flask Blueprints <https://flask.palletsprojects.com/en/stable/blueprints/>`_, 
*DashBlueprint*s enable piecewise construction of full applications by embedding functional components into 
a single unified layout. 

An example *Tool* is shown below with the same functionality as the minimal *Dash* application above:

.. code-block:: python

    from dash import dcc
    from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
    from fusion_tools.components.base import Tool
    import pandas as pd
    import plotly.express as px

    class BasicTool(Tool):

        title = 'Basic Tool'
        description = 'This is an example of a basic tool that can be added to a FUSION layout.'

        def __init__(self):

            super().__init__()

            self.df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv')
        
        def __str__(self):
            # The "__str__" method is not necessary to add (see Tool superclass), just here for illustration
            return self.title

        def load(self, component_prefix:int):
            # The "load" method is not necessary to add (see Tool superclass) in most cases
            self.component_prefix = component_prefix

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
                    children = self.title,
                    style = {'textAlign': 'center'}
                ),
                html.P(self.description),
                html.Hr(),
                dcc.Dropdown(
                    options = self.df.country.unique(),
                    value = 'Canada',
                    id = 'dropdown-selection'
                ),
                dcc.Graph(
                    id = 'graph-content'
                )
            ])

        
            # This line sets the layout to the "blueprint" object
            self.blueprint.layout = layout

        def get_callbacks(self):

            # Callbacks are added the the "blueprint" object instead of "app", referring to a method of the "BasicTool" component class.
            self.blueprint.callback(
                [
                    Input('dropdown-selection','value')
                ],
                [
                    Output('graph-content')
                ]
            )(self.update_graph)

        def update_graph(self, new_country):

            # Static data accessible through "BasicTool" (self) attribute
            # NOTE: If you intend to have multiple users of this component, I would recommend not storing data this way as you can run into errors when changes are made by different users at different times.
            country_data = self.df[self.df.country==new_country]
            new_plot = px.line(country_data, x = 'year', y = 'pop')

            return new_plot


This can then be added into a *fusion-tools* *Visualization* as below:

.. code-block:: python

    from fusion_tools import Visualization
    from basictool import BasicTool # if BasicTool is saved in a file called basictool.py

    new_vis = Visualization(
        components = [
            BasicTool()
        ]
    )

    new_vis.start()


*Pattern-matching callbacks*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
callbacks that contain *ALL* have to be a sequence (list or tuple).

Another use-case for pattern-matching callbacks is that it allows you to define callbacks for components 
which are not in the current app layout. This is useful for *DashBlueprint* objects as the blueprint layout 
may not be active at all times. NOTE: This is a somewhat irregular application of multi-page applications in 
Dash. For more information on multi-page applications see `this link <https://dash.plotly.com/urls>`.


"Linkage" in `fusion-tools`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In general, components in `fusion-tools` are designed to work in-tandem with other components in order to visualize, analyze, alter, etc. data. 
However, looking at the above specifications for callbacks, the question that emerges is how do we specify which component ids should interact with which? 

This is where the "self.component_prefix" and the `PrefixIdTransform` come into play.

When first starting a `fusion-tools` visualization, you will see these lines (with {} filled in):

.. code-block:: bash

    ------Creating Visualization with {n_rows} rows, {n_cols} columns, and {n_tabs} tabs--------
    ----------------- Components in the same {self.linkage} may communicate through callbacks---------

By default, components on the same page and in the same row communicate with each other through callbacks and access their respective component ids.

For a 2-row component with 2-columns per-row, inspecting the layout in the browser will show that the same component in row 1 
will have a component id like this:

*id={"index":0,"type":"0-example-component-id"}*

While in the second row, that same component will have a component id like this:

*id={"index":0,"type":"1-example-component-id"}*

The important takeaway here is that when determining interactivity (interactivability?) *Dash* first looks for 
matches of the component id "type", then at the component id "index". So if you are writing a new component 
to be incorporated into a `fusion-tools` layout, make sure you take this into consideration with dynamically 
generated components.

For example, if your component contains a button (ex: `dash_bootstrap_components.Button`) that creates a 
new text input (ex: `dash_core_components.Input`) and dropdown menu (ex: `dash_core_components.Dropdown`) you 
will have to do the following:

.. code-block:: python

    def new_inputs(self, button_clicks):

        new_row = dbc.Row([
            dbc.Col([
                dcc.Input(
                    id = {'type': f'{self.component_prefix}-input-component','index': 0}
                )
            ]),
            dbc.Col([
                dcc.Dropdown(
                    id = {'type': f'{self.component_prefix}-dropdown-component','index': 0}
                )
            ])
        ])

        return new_row


Alternatively, for larger returns, you can do this:

.. code-block:: python

    def new_inputs(self, button_clicks):

        new_row = dbc.Row([
            dbc.Col([
                dcc.Input(
                    id = {'type': 'input-component','index': 0}
                )
            ]),
            dbc.Col([
                dcc.Dropdown(
                    id = {'type': 'dropdown-component','index': 0}
                )
            ])
        ])

        # Modifies component ids of a layout in-place
        PrefixIdTransform(prefix = self.component_prefix).transform_layout(new_row)

        return new_row


Keep in mind, this example function is only set up to return the same row with empty components. If you want to 
create a new row every time that button is pressed (with or without modifying existing component contents), 
that is more complicated but still do-able. (Hint: Check out `OverlayOptions` "add_filter" method)


