"""Tool registry."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from ..config import get_settings
from . import (
    captcha_tools,
    interaction,
    javascript,
    navigation,
    network_tools,
    perception_tools,
    sessions_tools,
    system,
    tabs,
    vision,
)

logger = logging.getLogger("navigator.tools")


def register_tools(mcp: FastMCP) -> None:
    """Register all tool groups."""
    settings = get_settings()

    # ---- system --------------------------------------------------------
    mcp.tool(system.navigator_status)
    mcp.tool(system.usage_report)

    # ---- navigation ------------------------------------------------------
    mcp.tool(navigation.browser_navigate)
    mcp.tool(navigation.browser_navigate_back)
    mcp.tool(navigation.browser_navigate_forward)
    mcp.tool(navigation.browser_reload)
    mcp.tool(navigation.browser_wait_for)
    mcp.tool(navigation.browser_get_url)

    # ---- interaction -----------------------------------------------------
    mcp.tool(interaction.browser_click)
    mcp.tool(interaction.browser_click_text)
    mcp.tool(interaction.browser_fill)
    mcp.tool(interaction.browser_fill_form)
    mcp.tool(interaction.browser_select_option)
    mcp.tool(interaction.browser_hover)
    mcp.tool(interaction.browser_press_key)
    mcp.tool(interaction.browser_drag)
    mcp.tool(interaction.browser_upload_file)
    mcp.tool(interaction.browser_scroll)

    # ---- perception --------------------------------------------------------
    mcp.tool(perception_tools.browser_snapshot)
    mcp.tool(perception_tools.browser_find)
    mcp.tool(perception_tools.browser_extract_text)
    mcp.tool(perception_tools.browser_extract_html)
    mcp.tool(perception_tools.browser_extract_links)
    mcp.tool(perception_tools.browser_extract_forms)
    mcp.tool(perception_tools.browser_extract_tables)
    mcp.tool(perception_tools.browser_extract_meta)
    mcp.tool(perception_tools.browser_read_console)
    mcp.tool(perception_tools.browser_read_dialogs)

    # ---- tabs & sessions -----------------------------------------------------
    mcp.tool(tabs.browser_tab_list)
    mcp.tool(tabs.browser_tab_new)
    mcp.tool(tabs.browser_tab_select)
    mcp.tool(tabs.browser_tab_close)
    mcp.tool(sessions_tools.browser_session_list)
    mcp.tool(sessions_tools.browser_session_new)
    mcp.tool(sessions_tools.browser_session_close)
    mcp.tool(sessions_tools.browser_session_save_auth)

    # ---- vision ---------------------------------------------------------------
    mcp.tool(vision.browser_screenshot)
    mcp.tool(vision.browser_save_pdf)

    # ---- network ------------------------------------------------------------------
    mcp.tool(network_tools.browser_network_capture_start)
    mcp.tool(network_tools.browser_network_capture_stop)
    mcp.tool(network_tools.browser_network_list)
    mcp.tool(network_tools.browser_network_get)
    mcp.tool(network_tools.browser_network_block)
    mcp.tool(network_tools.browser_network_unblock)
    mcp.tool(network_tools.browser_discover_apis)
    mcp.tool(network_tools.browser_set_dialog_mode)
    mcp.tool(network_tools.browser_dialog_respond)

    # ---- javascript --------------------------------------------------------------------
    mcp.tool(javascript.browser_evaluate)

    # ---- captcha --------------------------------------------------------------------------
    mcp.tool(captcha_tools.browser_captcha_detect)
    mcp.tool(captcha_tools.browser_captcha_solve)
    mcp.tool(captcha_tools.browser_captcha_manual_wait)

    logger.info(
        "tool registration complete (all features unlocked, stealth=%s)",
        settings.stealth,
    )
