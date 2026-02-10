import logging
from telegram import ChatMember

logger = logging.getLogger(__name__)

async def check_membership(user_id, context, target_channel):
    """
    Check if a user is a member of the target channel.
    
    Args:
        user_id (int): The ID of the user to check.
        context (telegram.ext.ContextTypes.DEFAULT_TYPE): The context object from the update.
        target_channel (str): The username or ID of the channel to check membership for.
        
    Returns:
        bool: True if the user is a member, False otherwise.
    """
    try:
        member = await context.bot.get_chat_member(target_channel, user_id)
        valid_statuses = [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
            "creator",
            "administrator",
            "member"
        ]
        is_member = member.status in valid_statuses
        if not is_member:
            logger.info(f"❌ User {user_id} not member. Status: {member.status}")
        return is_member
    except Exception as e:
        logger.error(f"❌ Membership check error: {e}")
        return False
