"""Components and classes related to user surveys hosted in DSA"""

# Dash imports
from dash_extensions.enrich import (
    html,
)

from fusion_tools.components.base import BaseSchema, DSATool


class SurveyType(BaseSchema):
    def __init__(
        self,
        description: str = "",
        question_list: list = [],
        users: list = [],
        storage_folder: str = "",
    ):
        """Type of survey to expose to select users.

        :param question_list: List of questions to include in the survey as well as expected types for responses.
        :type question_list: list, optional
        :param users: List of usernames that the survey is accessible to.
        :type users: list, optional
        :param storage_folder: Id of folder that will contain survey results
        :type storage_folder: str, optional

        """

        self.description = description
        self.question_list = question_list
        self.users = users
        self.storage_folder = storage_folder


class DSASurvey(DSATool):
    """Handler for DSASurvey component, letting users add a survey questionnaire to a layout (with optional login for targeting specific users).

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """

    title = "DSA Survey"
    description = ""

    def __init__(self, dsa_handler, survey: SurveyType):

        self.dsa_handler = dsa_handler
        self.survey = survey

    def gen_layout(self, session_data: dict | None):

        layout = html.Div(
            [
                dbc.Card(
                    dbc.CardBody([dbc.Row(html.H3(self.title)), html.Hr(), dbc.Row()])
                )
            ]
        )

        self.blueprint.layout = layout

    def get_callbacks(self):

        # Callback for submitting survey responses
        # Callback for admins seeing current survey responses
        # Callback for admins to download current survey results
        # Callback for admins to add usernames to the survey
        pass
