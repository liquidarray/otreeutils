"""
Survey extensions that allows to define survey questions with a simple data structure and then automatically creates
the necessary model fields and pages.

March 2019, Markus Konrad <markus.konrad@wzb.eu>
"""

from functools import partial
from collections import OrderedDict

from otree.api import BasePlayer, widgets, models

from .pages import ExtendedPage


def generate_likert_field(labels, widget=None):
    """
    Return a function which generates a new `IntegerField` with a Likert scale between 1 and `len(labels)`. Use
    `widget` as selection widget (default is `RadioSelectHorizontal`).

    Example with a 4-point Likert scale:

    ```
    likert_4_field = generate_likert_field("Strongly disagree", "Disagree",  "Agree", "Strongly agree")

    class Player(BasePlayer):
        q1 = likert_4_field()
    ```
    """
    if not widget:
        widget = widgets.RadioSelectHorizontal

    choices = list(zip(range(1, len(labels) + 1), labels))

    return partial(models.IntegerField, widget=widget, choices=choices)


def generate_likert_table(likert_labels, questions, form_name=None, help_texts=None, widget=None, **kwargs):
    """
    Generate a table with Likert scales between 1 and `len(likert_labels)` in each row for questions supplied with
    `questions` as list of tuples (field name, field label).
    Optionally provide `help_texts` which is a list of help texts for each question (hence must be of same length
    as `questions`.
    Optionally set `widget` (default is `RadioSelect`).
    """
    if not help_texts:
        help_texts = [''] * len(questions)

    if not widget:
        widget = widgets.RadioSelect

    if len(help_texts) != len(questions):
        raise ValueError('Number of questions must be equal to number of help texts.')

    likert_field = generate_likert_field(likert_labels, widget=widget)

    fields = []
    for (field_name, field_label), help_text in zip(questions, help_texts):
        fields.append((field_name, {
            'help_text': help_text,
            'label': field_label,
            'field': likert_field(),
        }))

    form_def = {'form_name': form_name, 'fields': fields, 'render_type': 'table', 'header_labels': likert_labels}
    form_def.update(dict(**kwargs))

    return form_def


def create_player_model_for_survey(module, survey_definitions, base_cls=None):
    """
    Dynamically create a player model in module <module> with a survey definitions and a base player class.
    Parameter survey_definitions is a list, where each list item is a survey definition for a single page.
    Each survey definition for a single page consists of list of field name, question definition tuples.
    Each question definition has a "field" (oTree model field class) and a "text" (field label).

    Returns the dynamically created player model with the respective fields (class attributes).
    """
    if base_cls is None:
        base_cls = BasePlayer

    model_attrs = {
        '__module__': module,
        '_survey_defs': survey_definitions,
    }

    # collect fields
    for survey_page in survey_definitions:
        for fielddef in survey_page['survey_fields']:
            if isinstance(fielddef, dict):
                for field_name, qdef in fielddef['fields']:
                    model_attrs[field_name] = qdef['field']
            else:
                field_name, qdef = fielddef
                model_attrs[field_name] = qdef['field']

    # dynamically create model
    model_cls = type('Player', (base_cls, _SurveyModelMixin), model_attrs)

    return model_cls


class _SurveyModelMixin(object):
    """Little mix-in for dynamically generated survey model classes"""
    @classmethod
    def get_survey_definitions(cls):
        return cls._survey_defs


def setup_survey_pages(form_model, survey_pages):
    """
    Helper function to set up a list of survey pages with a common form model
    (a dynamically generated survey model class).
    """
    for i, page in enumerate(survey_pages):
        page.setup_survey(form_model, i)   # call setup function with model class and page index


class SurveyPage(ExtendedPage):
    """
    Common base class for survey pages.
    Displays a form for the survey questions that were defined for this page.
    """
    FORM_OPTS_DEFAULT = {
        'render_type': 'standard',
        'form_help_initial': '',
        'form_help_final': '',
    }
    template_name = 'otreeutils/SurveyPage.html'
    field_labels = {}
    field_help_text = {}
    field_forms = {}
    forms_opts = {}

    @classmethod
    def setup_survey(cls, player_cls, page_idx):
        """Setup a survey page using model class <player_cls> and survey definitions for page <page_idx>."""
        survey_defs = player_cls.get_survey_definitions()[page_idx]
        cls.form_model = player_cls
        cls.page_title = survey_defs['page_title']

        cls.form_fields = []

        def add_field(cls, form_name, field_name, qdef):
            cls.field_labels[field_name] = qdef.get('text', qdef.get('label', ''))
            cls.field_help_text[field_name] = qdef.get('help_text', '')
            cls.form_fields.append(field_name)
            cls.field_forms[field_name] = form_name

        form_idx = 0
        for fielddef in survey_defs['survey_fields']:
            form_name = 'form%d_%d' % (page_idx, form_idx)

            cls.forms_opts[form_name] = cls.FORM_OPTS_DEFAULT.copy()

            if isinstance(fielddef, dict):
                cls.forms_opts[form_name].update({k: v for k, v in fielddef.items()
                                                  if k not in ('fields', 'form_name')})

                for field_name, qdef in fielddef['fields']:
                    form_name = fielddef.get('form_name', None) or form_name
                    add_field(cls, form_name, field_name, qdef)

                form_idx += 1
            else:
                add_field(cls, form_name, *fielddef)

    def get_context_data(self, **kwargs):
        ctx = super(SurveyPage, self).get_context_data(**kwargs)

        form = kwargs['form']

        survey_forms = OrderedDict()
        for field_name, field in form.fields.items():
            form_name = self.field_forms[field_name]

            field.label = self.field_labels[field_name]
            field.help_text = self.field_help_text[field_name]

            if form_name not in survey_forms:
                survey_forms[form_name] = {'fields': [], 'form_opts': self.forms_opts.get(form_name, {})}

            survey_forms[form_name]['fields'].append(field_name)

        ctx.update({
            'base_form': form,
            'survey_forms': survey_forms,
        })

        return ctx
