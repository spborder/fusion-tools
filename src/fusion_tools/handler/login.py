"""DSALoginComponent
"""

import json

from typing_extensions import Union

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import callback, ctx, ALL, MATCH, exceptions, no_update
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.components.base import DSATool


class DSALoginComponent(DSATool):
    """Handler for DSALoginComponent, enabling login to the running DSA instance

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None

    """

    title = 'DSA Login Component'
    description = ''

    def __init__(self,
                 handler,
                 default_user: Union[dict,None] = None
                ):
        
        super().__init__()
        self.handler = handler
        self.default_user = default_user

        self.modal_size = 'lg'

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        current_user_children = ''
        if 'user' in session_data:
            current_user_children = f'Welcome, {session_data.get("user",{}).get("firstName")} ({session_data.get("user",{}).get("login","")})!'
            logout_button_disable = False

        else:
            current_user_children = 'Welcome, Guest!'
            logout_button_disable = True


        layout = html.Div([
            html.H4(
                id = {'type': 'dsa-login-current-user','index': 0},
                children = [
                    current_user_children
                ]
            ),
            html.Hr(),
            html.Div(
                id = {'type': 'dsa-login-div','index': 0},
                children = [
                    dbc.Stack([
                        dbc.Button(
                            'Login',
                            className = 'd-grid col-6 mx-auto',
                            color = 'success',
                            id = {'type': 'dsa-login-button','index': 0}
                        ),
                        dbc.Tooltip(
                            'Login to view data stored in the cloud!',
                            target = {'type': 'dsa-login-button','index': 0},
                            placement='top'
                        ),
                        dbc.Button(
                            'Create an Account',
                            className = 'd-grid col-6 mx-auto',
                            color = 'warning',
                            id = {'type': 'dsa-login-create-account-button','index': 0}
                        ),
                        dbc.Tooltip(
                            'Create an account in order to upload slides to the DSA instance, to access user surveys, or to share data!',
                            target = {'type': 'dsa-login-create-account-button','index': 0},
                            placement='top'
                        )
                    ],direction='horizontal',gap=2)
                ]
            )
        ],style = {'padding': '10px 10px 10px 10px'})

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix).transform_layout(layout)

        return layout

    def get_callbacks(self):

        # Callback for selecting Login vs. Create Account
        self.blueprint.callback(
            [
                Input({'type': 'dsa-login-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-login-create-account-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-login-back-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'dsa-login-div','index': ALL},'children')
            ]
        )(self.display_login_fields)

        # Callback for clicking Login button with username and password
        self.blueprint.callback(
            [
                Input({'type': 'dsa-login-login-submit','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-login-username-input','index': ALL},'value'),
                State({'type': 'dsa-login-password-input','index': ALL},'value'),
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ],
            [
                Output({'type': 'dsa-login-username-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-password-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-login-error-div','index':ALL},'children'),
                Output('anchor-vis-store','data'),
                Output('anchor-vis-memory-store','data')
            ]
        )(self.submit_login)

        # Callback for clicking Create Account with input details
        self.blueprint.callback(
            [
                Input({'type':'dsa-login-create-account-submit','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-login-firstname-input','index': ALL},'value'),
                State({'type': 'dsa-login-lastname-input','index': ALL},'value'),
                State({'type': 'dsa-login-email-input','index': ALL},'value'),
                State({'type': 'dsa-login-username-input','index': ALL},'value'),
                State({'type': 'dsa-login-password-input','index': ALL},'value'),
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ],
            [
                Output({'type': 'dsa-login-email-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-username-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-password-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-create-account-error-div','index': ALL},'children'),
                Output('anchor-vis-store','data'),
                Output('anchor-vis-memory-store','data')
            ]
        )(self.submit_create_account)
        
    def display_login_fields(self, login_clicked, create_account_clicked, back_clicked):
        """Displaying login fields depending on if login, create account, or back is clicked

        :param login_clicked: Login button clicked
        :type login_clicked: list
        :param create_account_clicked: Create Account button clicked
        :type create_account_clicked: list
        :param back_clicked: Back icon clicked
        :type back_clicked: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        if 'dsa-login-button' in ctx.triggered_id['type']:
            # Create input fields for "username" and "password" and a button for Login
            new_children = html.Div([
                dbc.Row([
                    dbc.Col(
                        html.A(
                            dbc.Stack([
                                html.P(
                                    html.I(
                                        className = 'fa-solid fa-arrow-left',
                                        style = {'marginRight':'5px'}
                                    )
                                ),
                                html.P(
                                    'Back'
                                )
                            ],direction='horizontal'),
                            id = {'type': f'{self.component_prefix}-dsa-login-back-icon','index': 0},
                            n_clicks = 0
                        )
                    )
                ]),
                dbc.Stack([
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Username: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-username-input','index': 0},
                            placeholder='username',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-z0-9]+$'
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-username-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Password: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-password-input','index': 0},
                            type = 'password',
                            required = True,
                            value = [],
                            maxLength = 1000
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-password-error-div','index': 0},
                        children = []
                    ),
                    dbc.Button(
                        'Login!',
                        className = 'd-grid col-12 mx-auto',
                        color = 'primary',
                        id = {'type': f'{self.component_prefix}-dsa-login-login-submit','index': 0},
                        n_clicks = 0
                    ),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-login-error-div','index': 0},
                        children = []
                    )
                ],direction = 'vertical',gap=1)
            ])

        elif 'dsa-login-create-account-button' in ctx.triggered_id['type']:
            # Create input fields for "username" and "password" and a button for Login
            new_children = html.Div([
                dbc.Row([
                    dbc.Col(
                        html.A(
                            dbc.Stack([
                                html.P(
                                    html.I(
                                        className = 'fa-solid fa-arrow-left',
                                        style = {'marginRight':'2px'}
                                    )
                                ),
                                html.P(
                                    'Back'
                                )
                            ],direction='horizontal'),
                            id = {'type': f'{self.component_prefix}-dsa-login-back-icon','index': 0},
                            n_clicks = 0
                        )
                    )
                ]),
                dbc.Stack([
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'First Name: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-firstname-input','index': 0},
                            placeholder='First Name',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-zA-Z]+$'
                        )
                    ]),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Last Name: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-lastname-input','index':0},
                            placeholder = 'Last Name',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-zA-Z]+$'
                        )
                    ]),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Email: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-email-input','index':0},
                            placeholder = 'email address',
                            type = 'email',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-email-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Username: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-username-input','index': 0},
                            placeholder='username',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-z0-9]+$'
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-username-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Password: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-password-input','index': 0},
                            type = 'password',
                            required = True,
                            value = [],
                            maxLength = 1000
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-password-error-div','index': 0},
                        children = []
                    ),
                    dbc.Button(
                        'Login!',
                        className = 'd-grid col-12 mx-auto',
                        color = 'primary',
                        id = {'type': f'{self.component_prefix}-dsa-login-create-account-submit','index': 0},
                        n_clicks = 0
                    ),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-create-account-error-div','index':0},
                        children = []
                    )
                ],direction='vertical',gap=1)
            ])
    
        elif 'dsa-login-back-icon' in ctx.triggered_id['type']:
            new_children = dbc.Stack([
                dbc.Button(
                    'Login',
                    className = 'd-grid col-6 mx-auto',
                    color = 'success',
                    id = {'type': f'{self.component_prefix}-dsa-login-button','index': 0}
                ),
                dbc.Tooltip(
                    'Login to view data stored in the cloud!',
                    target = {'type': f'{self.component_prefix}-dsa-login-button','index': 0},
                    placement='top'
                ),
                dbc.Button(
                    'Create an Account',
                    className = 'd-grid col-6 mx-auto',
                    color = 'warning',
                    id = {'type': f'{self.component_prefix}-dsa-login-create-account-button','index': 0}
                ),
                dbc.Tooltip(
                    'Create an account in order to upload slides to the DSA instance, to access user surveys, or to share data!',
                    target = {'type': f'{self.component_prefix}-dsa-create-account-button','index': 0},
                    placement='top'
                )
            ],direction='horizontal',gap=2)

        return [new_children]
    
    def submit_login(self, login_clicked,username_input, password_input, session_data, in_memory_store):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        in_memory_store = json.loads(in_memory_store)
        
        username_input = get_pattern_matching_value(username_input)
        password_input = get_pattern_matching_value(password_input)

        if username_input is None or username_input == '':
            username_error_div = dbc.Alert('Make sure to enter a username!',color = 'danger')
        else:
            username_error_div = []
        
        if password_input is None or password_input == '':
            password_error_div = dbc.Alert('Make sure to enter your password!',color = 'danger')
        else:
            password_error_div = []

        if not any([i is None or i=='' for i in [username_input,password_input]]):
            new_login_output = self.handler.authenticate_new(
                username = username_input,
                password= password_input
            )
            if not type(new_login_output)==str:
                session_data['user']['external'] = new_login_output
                in_memory_store['user']['external'] = new_login_output
                login_error_div = dbc.Alert(
                    f'External Login: {new_login_output.get("login")} has been added to your account!',
                    color = 'success'
                )

                # Updating user in database
                updated_user = self.database.get_create(
                    table_name = 'user',
                    inst_id = session_data.get('user').get('id'),
                    kwargs = {
                        k:v
                        for k,v in session_data.get('user').items()
                        if not k=='id'
                    }
                )

                session_data = json.dumps(session_data)
                in_memory_store = json.dumps(in_memory_store)


            else:
                session_data = no_update
                in_memory_store = no_update
                login_error_div = dbc.Alert(f'Error logging in with username: {username_input}',color = 'danger')
        else:
            session_data = no_update
            in_memory_store = no_update
            login_error_div = []
        
        return [username_error_div], [password_error_div], [login_error_div], session_data, in_memory_store

    def submit_create_account(self, clicked,firstname_input, lastname_input, email_input, username_input, password_input,session_data,in_memory_store):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        in_memory_store = json.loads(in_memory_store)
        
        firstname_input = get_pattern_matching_value(firstname_input)
        lastname_input = get_pattern_matching_value(lastname_input)
        username_input = get_pattern_matching_value(username_input)
        password_input = get_pattern_matching_value(password_input)
        email_input = get_pattern_matching_value(email_input)

        if username_input is None or username_input=='':
            username_error_div = dbc.Alert('Make sure to enter a username!',color = 'danger')
        else:
            username_error_div = []
        
        if password_input is None or password_input == '':
            password_error_div = dbc.Alert('Make sure to enter your password!',color = 'danger')
        else:
            password_error_div = []

        if email_input is None or email_input == '':
            email_error_div = dbc.Alert('Make sure to enter a valid email address! (And not the same as any other account)',color = 'danger')
        else:
            email_error_div = []

        if not any([i is None or i =='' for i in [firstname_input,lastname_input,email_input,username_input,password_input]]):
            create_user_output = self.handler.create_new_user(
                username = username_input,
                password = password_input,
                email = email_input,
                firstName = firstname_input,
                lastName= lastname_input
            )
            if create_user_output:
                session_data['user']['external'] = create_user_output
                session_data = json.dumps(session_data)
                in_memory_store['user']['external'] = create_user_output
                in_memory_store = json.dumps(in_memory_store)
                create_account_error_div = []
            else:
                session_data = no_update
                in_memory_store = no_update
                create_account_error_div = dbc.Alert(f'Error creating account with username: {username_input}',color = 'danger')
        else:
            session_data = no_update
            in_memory_store = no_update
            create_account_error_div = []
        
        return [username_error_div],[password_error_div],[email_error_div], [create_account_error_div], session_data, in_memory_store
        

