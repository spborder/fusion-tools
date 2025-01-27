"""Generating UserSurvey components for FUSION
"""

from fusion_tools.handler import SurveyType


def get_surveys(*args):

    general_user_survey = SurveyType(
        question_list=[],
        users = [],
        storage_folder=[]
    )

    return [
        general_user_survey
    ]

