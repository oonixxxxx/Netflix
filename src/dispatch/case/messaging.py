"""
.. module: dispatch.case.messaging
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
"""

import logging


from sqlalchemy.orm import Session

from dispatch.database.core import resolve_attr
from dispatch.document import service as document_service
from dispatch.case.models import Case, CaseRead
from dispatch.conversation.enums import ConversationCommands
from dispatch.entity_type.models import EntityType
from dispatch.messaging.strings import (
    CASE_CLOSE_REMINDER,
    CASE_TRIAGE_REMINDER,
    CASE_NOTIFICATION,
    CASE_NOTIFICATION_COMMON,
    CASE_NAME_WITH_ENGAGEMENT,
    CASE_NAME_WITH_ENGAGEMENT_NO_SELF_JOIN,
    CASE_NAME,
    CASE_ASSIGNEE,
    CASE_STATUS_CHANGE,
    CASE_TYPE_CHANGE,
    CASE_SEVERITY_CHANGE,
    CASE_PRIORITY_CHANGE,
    CASE_VISIBILITY_CHANGE,
    CASE_CLOSED_RATING_FEEDBACK_NOTIFICATION,
    MessageType,
    generate_welcome_message,
)
from dispatch.config import DISPATCH_UI_URL
from dispatch.email_templates.models import EmailTemplates
from dispatch.plugin import service as plugin_service
from dispatch.plugins.dispatch_slack.models import SubjectMetadata
from dispatch.plugins.dispatch_slack.case.enums import CaseNotificationActions
from dispatch.event import service as event_service
from dispatch.notification import service as notification_service

from .enums import CaseStatus

log = logging.getLogger(__name__)


def send_case_close_reminder(case: Case, db_session: Session) -> None:
    """
    Sends a direct message to the assignee reminding them to close the case if possible.
    """
    message_text = "Case Close Reminder"
    message_template = CASE_CLOSE_REMINDER

    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if plugin is None:
        log.warning("Case close reminder message not sent. No conversation plugin enabled.")
        return
    if case.assignee is None:
        log.warning(f"Case close reminder message not sent. No assignee for {case.name}.")
        return

    items = [
        {
            "name": case.name,
            "dispatch_ui_case_url": f"{DISPATCH_UI_URL}/{case.project.organization.name}/cases/{case.name}",  # noqa
            "title": case.title,
            "status": case.status,
        }
    ]

    plugin.instance.send_direct(
        case.assignee.individual.email,
        message_text,
        message_template,
        MessageType.case_status_reminder,
        items=items,
    )

    log.debug(f"Case close reminder sent to {case.assignee.individual.email}.")


def send_case_triage_reminder(case: Case, db_session: Session) -> None:
    """
    Sends a direct message to the assignee reminding them to triage the case if possible.
    """
    message_text = "Case Triage Reminder"
    message_template = CASE_TRIAGE_REMINDER

    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if plugin is None:
        log.warning("Case triage reminder message not sent. No conversation plugin enabled.")
        return

    if case.assignee is None:
        log.warning(f"Case triage reminder message not sent. No assignee for {case.name}.")
        return

    items = [
        {
            "name": case.name,
            "title": case.title,
            "status": case.status,
            "dispatch_ui_case_url": f"{DISPATCH_UI_URL}/{case.project.organization.name}/cases/{case.name}",  # noqa
        }
    ]

    plugin.instance.send_direct(
        case.assignee.individual.email,
        message_text,
        message_template,
        MessageType.case_status_reminder,
        items=items,
    )

    log.debug(f"Case triage reminder sent to {case.assignee.individual.email}.")


def send_case_created_notifications(case: Case, db_session: Session):
    """Sends case created notifications."""
    notification_template = CASE_NOTIFICATION.copy()

    if case.status != CaseStatus.closed:
        if case.project.allow_self_join:
            notification_template.insert(0, CASE_NAME_WITH_ENGAGEMENT)
        else:
            notification_template.insert(0, CASE_NAME_WITH_ENGAGEMENT_NO_SELF_JOIN)
    else:
        notification_template.insert(0, CASE_NAME)

    case_description = (
        case.description if len(case.description) <= 500 else f"{case.description[:500]}..."
    )

    notification_kwargs = {
        "name": case.name,
        "title": case.title,
        "description": case_description,
        "visibility": case.visibility,
        "status": case.status,
        "type": case.case_type.name,
        "type_description": case.case_type.description,
        "severity": case.case_severity.name,
        "severity_description": case.case_severity.description,
        "priority": case.case_priority.name,
        "priority_description": case.case_priority.description,
        "reporter_fullname": case.reporter.individual.name,
        "reporter_team": case.reporter.team,
        "reporter_weblink": case.reporter.individual.weblink,
        "assignee_fullname": case.assignee.individual.name,
        "assignee_team": case.assignee.team,
        "assignee_weblink": case.assignee.individual.weblink,
        "document_weblink": resolve_attr(case, "case_document.weblink"),
        "storage_weblink": resolve_attr(case, "storage.weblink"),
        "ticket_weblink": resolve_attr(case, "ticket.weblink"),
        "contact_fullname": case.assignee.individual.name,
        "contact_weblink": case.assignee.individual.weblink,
        "case_id": case.id,
        "organization_slug": case.project.organization.slug,
    }

    notification_params = {
        "text": "Case Notification",
        "type": MessageType.case_notification,
        "template": notification_template,
        "kwargs": notification_kwargs,
    }

    notification_service.filter_and_send(
        db_session=db_session,
        project_id=case.project.id,
        class_instance=case,
        notification_params=notification_params,
    )

    event_service.log_case_event(
        db_session=db_session,
        source="Dispatch Core App",
        description="Case notifications sent",
        case_id=case.id,
    )

    log.debug("Case created notifications sent.")


def send_case_update_notifications(case: Case, previous_case: CaseRead, db_session: Session):
    """Sends notifications about case changes."""
    notification_text = "Case Notification"
    notification_type = MessageType.case_notification
    notification_template = CASE_NOTIFICATION_COMMON.copy()

    change = False
    if previous_case.status != case.status:
        change = True
        notification_template.append(CASE_STATUS_CHANGE)
        if previous_case.case_type.name != case.case_type.name:
            notification_template.append(CASE_TYPE_CHANGE)

        if previous_case.case_severity.name != case.case_severity.name:
            notification_template.append(CASE_SEVERITY_CHANGE)

        if previous_case.case_priority.name != case.case_priority.name:
            notification_template.append(CASE_PRIORITY_CHANGE)
    else:
        if case.status != CaseStatus.closed:
            if previous_case.case_type.name != case.case_type.name:
                change = True
                notification_template.append(CASE_TYPE_CHANGE)

            if previous_case.case_severity.name != case.case_severity.name:
                change = True
                notification_template.append(CASE_SEVERITY_CHANGE)

            if previous_case.case_priority.name != case.case_priority.name:
                change = True
                notification_template.append(CASE_PRIORITY_CHANGE)

            if previous_case.visibility != case.visibility:
                change = True
                notification_template.append(CASE_VISIBILITY_CHANGE)

    if not change:
        # we don't need to send notifications
        log.debug("Case updated notifications not sent. No changes were made.")
        return

    notification_template.append(CASE_ASSIGNEE)

    # we send an update to the case conversation if the case is active or stable
    if case.status != CaseStatus.closed:
        case_conversation_notification_template = notification_template.copy()
        case_conversation_notification_template.insert(0, CASE_NAME)

        convo_plugin = plugin_service.get_active_instance(
            db_session=db_session, project_id=case.project.id, plugin_type="conversation"
        )
        if convo_plugin:
            convo_plugin.instance.send(
                case.conversation.channel_id,
                notification_text,
                case_conversation_notification_template,
                notification_type,
                assignee_fullname=case.assignee.individual.name,
                assignee_team=case.assignee.team,
                assignee_weblink=case.assignee.individual.weblink,
                case_priority_new=case.case_priority.name,
                case_priority_old=previous_case.case_priority.name,
                case_severity_new=case.case_severity.name,
                case_severity_old=previous_case.case_severity.name,
                case_status_new=case.status,
                case_status_old=previous_case.status,
                case_type_new=case.case_type.name,
                case_type_old=previous_case.case_type.name,
                case_visibility_new=case.visibility,
                case_visibility_old=previous_case.visibility,
                name=case.name,
                ticket_weblink=case.ticket.weblink,
                title=case.title,
                escalated_to_incident=case.incidents[0] if case.incidents else None,
            )
        else:
            log.debug(
                "Case updated notification not sent to case conversation. No conversation plugin enabled."  # noqa
            )

    # we send a notification to the notification conversations and emails
    fyi_notification_template = notification_template.copy()
    if case.status != CaseStatus.closed:
        if case.project.allow_self_join:
            fyi_notification_template.insert(0, CASE_NAME_WITH_ENGAGEMENT)
        else:
            fyi_notification_template.insert(0, CASE_NAME_WITH_ENGAGEMENT_NO_SELF_JOIN)
    else:
        fyi_notification_template.insert(0, CASE_NAME)

    notification_kwargs = {
        "assignee_fullname": case.assignee.individual.name,
        "assignee_team": case.assignee.team,
        "assignee_weblink": case.assignee.individual.weblink,
        "contact_fullname": case.assignee.individual.name,
        "contact_weblink": case.assignee.individual.weblink,
        "case_id": case.id,
        "case_priority_new": case.case_priority.name,
        "case_priority_old": previous_case.case_priority.name,
        "case_severity_new": case.case_severity.name,
        "case_severity_old": previous_case.case_severity.name,
        "case_status_new": case.status,
        "case_status_old": previous_case.status,
        "case_type_new": case.case_type.name,
        "case_type_old": previous_case.case_type.name,
        "case_visibility_new": case.visibility,
        "case_visibility_old": previous_case.visibility,
        "name": case.name,
        "organization_slug": case.project.organization.slug,
        "ticket_weblink": resolve_attr(case, "ticket.weblink"),
        "title": case.title,
        "escalated_to_incident": case.incidents[0] if case.incidents else None,
    }

    notification_params = {
        "text": notification_text,
        "type": notification_type,
        "template": fyi_notification_template,
        "kwargs": notification_kwargs,
    }

    notification_service.filter_and_send(
        db_session=db_session,
        project_id=case.project.id,
        class_instance=case,
        notification_params=notification_params,
    )

    log.debug("Case updated notifications sent.")


def send_case_welcome_participant_message(
    *,
    participant_email: str,
    case: Case,
    db_session: Session,
    welcome_template: EmailTemplates | None = None,
):
    if not case.dedicated_channel:
        return

    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )

    if not plugin:
        log.warning("Case participant welcome message not sent. No conversation plugin enabled.")
        return

    # we send the ephemeral message
    message_kwargs = {
        "name": case.name,
        "title": case.title,
        "description": case.description,
        "visibility": case.visibility,
        "status": case.status,
        "type": case.case_type.name,
        "type_description": case.case_type.description,
        "severity": case.case_severity.name,
        "severity_description": case.case_severity.description,
        "priority": case.case_priority.name,
        "priority_description": case.case_priority.description,
        "assignee_fullname": case.assignee.individual.name,
        "assignee_team": case.assignee.team,
        "assignee_weblink": case.assignee.individual.weblink,
        "reporter_fullname": case.reporter.individual.name if case.reporter else None,
        "reporter_team": case.reporter.team if case.reporter else None,
        "reporter_weblink": case.reporter.individual.weblink if case.reporter else None,
        "document_weblink": resolve_attr(case, "case_document.weblink"),
        "storage_weblink": resolve_attr(case, "storage.weblink"),
        "ticket_weblink": resolve_attr(case, "ticket.weblink"),
        "conference_weblink": resolve_attr(case, "conference.weblink"),
        "conference_challenge": resolve_attr(case, "conference.conference_challenge"),
    }
    faq_doc = document_service.get_incident_faq_document(
        db_session=db_session, project_id=case.project_id
    )
    if faq_doc:
        message_kwargs.update({"faq_weblink": faq_doc.weblink})

    conversation_reference = document_service.get_conversation_reference_document(
        db_session=db_session, project_id=case.project_id
    )
    if conversation_reference:
        message_kwargs.update(
            {"conversation_commands_reference_document_weblink": conversation_reference.weblink}
        )

    plugin.instance.send_ephemeral(
        conversation_id=case.conversation.channel_id,
        user=participant_email,
        text=f"Welcome to {case.name}",
        message_template=generate_welcome_message(welcome_template, is_incident=False),
        notification_type=MessageType.case_participant_welcome,
        **message_kwargs,
    )

    log.debug(f"Welcome ephemeral message sent to {participant_email}.")


def send_event_update_prompt_reminder(case: Case, db_session: Session) -> None:
    """
    Sends an ephemeral message to the assignee reminding them to update the visibility, title, priority
    """
    message_text = "Event Triage Reminder"

    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if plugin is None:
        log.warning("Event update prompt message not sent. No conversation plugin enabled.")
        return
    if case.assignee is None:
        log.warning(f"Event update prompt message not sent. No assignee for {case.name}.")
        return

    button_metadata = SubjectMetadata(
        type="case",
        organization_slug=case.project.organization.slug,
        id=case.id,
    ).json()

    plugin.instance.send_ephemeral(
        conversation_id=case.conversation.channel_id,
        user=case.assignee.individual.email,
        text=message_text,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f"Update the title, priority, case type and visibility during triage of this security event.",  # noqa
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Update Case"},
                        "action_id": CaseNotificationActions.update,
                        "style": "primary",
                        "value": button_metadata
                    }
                ],
            },
        ],
    )

    log.debug(f"Security Event update reminder sent to {case.assignee.individual.email}.")

def send_event_paging_message(case: Case, db_session: Session, oncall_name: str) -> None:
    """
    Sends a message to the case conversation channel to notify the reporter that they can engage
    with oncall if they need immediate assistance.
    """
    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if plugin is None:
        log.warning("Event paging message not sent, no conversation plugin enabled.")
        return

    notification_text = "Case can be engaged with oncall."
    notification_type = MessageType.incident_notification

    engage_oncall_command = plugin.instance.get_command_name(ConversationCommands.engage_oncall)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Response Expectation*"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"""Event reported. Team will respond during business hours. For urgent assistance, type `{engage_oncall_command}` in this channel and select "Page" to contact `{oncall_name}`.""",
            },
        },
    ]

    try:
        plugin.instance.send(
            case.conversation.channel_id,
            notification_text,
            [],
            notification_type,
            blocks=blocks,
        )
    except Exception as e:
        log.error(f"Error sending event paging message: {e}")


def send_case_rating_feedback_message(case: Case, db_session: Session):
    """
    Sends a direct message to all case participants asking
    them to rate and provide feedback about the case.
    """
    notification_text = "Case Rating and Feedback"
    notification_template = CASE_CLOSED_RATING_FEEDBACK_NOTIFICATION

    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if not plugin:
        log.warning("Case rating and feedback message not sent, no conversation plugin enabled.")
        return

    items = [
        {
            "case_id": case.id,
            "organization_slug": case.project.organization.slug,
            "name": case.name,
            "title": case.title,
            "ticket_weblink": case.ticket.weblink,
        }
    ]

    for participant in case.participants:
        try:
            plugin.instance.send_direct(
                participant.individual.email,
                notification_text,
                notification_template,
                MessageType.case_rating_feedback,
                items=items,
            )
        except Exception as e:
            # if one fails we don't want all to fail
            log.exception(e)

    log.debug("Case rating and feedback message sent to all participants.")


def send_entity_update_notification(*, db_session: Session, entity_type: EntityType, case: Case):
    plugin = plugin_service.get_active_instance(
        db_session=db_session, project_id=case.project.id, plugin_type="conversation"
    )
    if not plugin:
        log.warning("Entity update notification not sent, no conversation plugin enabled.")
        return

    if case.dedicated_channel or not case.has_thread:
        log.warning("Entity update notification not sent, can only send to case threads.")
        return

    notification_text = "Entity Update Notification"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{entity_type.name} created. You can now create a snooze for entities of this type.",
            },
        },
    ]

    plugin.instance.send(
        conversation_id=case.conversation.channel_id,
        text=notification_text,
        message_template=[],
        notification_type=MessageType.entity_update,
        blocks=blocks,
        ts=case.conversation.thread_id,
    )

    log.debug("Entity update notification sent to all participants.")
