#!/usr/bin/env python3
"""
Telegram bot for income-node-runner control panel.
Commands:
  /help            - show all commands
  /nodes           - list all nodes + proxy
  /start_all       - start all nodes
  /stop_all        - stop all nodes
  /setup           - setup nodes from proxies.txt
  /start <id...>   - start specific node(s)
  /stop <id...>    - stop specific node(s)
  /delete <id...>  - delete specific node(s)
  /delete_all      - delete ALL nodes (requires confirm)
  /add <proxy>     - add proxy and create node
  /remove <proxy>  - remove proxy and delete node
  /earnapp         - collect earnapp links
  /update_props    - sync properties.conf to all nodes
  /web_status      - check if web server is running
  /web_start       - start web server in background
  /web_stop        - stop web server
  /docker_ps       - list running docker containers
"""

import json
import logging
import os
import subprocess
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_SH = os.path.join(SCRIPT_DIR, "main.sh")
START_SH = os.path.join(SCRIPT_DIR, "start.sh")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIRM_DELETE_ALL = 1


def load_config() -> dict:
    if not os.path.isfile(CONFIG_PATH):
        logger.error("config.json not found at %s", CONFIG_PATH)
        logger.error("Copy config.example.json to config.json and fill in the values.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()
BOT_TOKEN: str = CFG["bot_token"]
ALLOWED_USERS: set[int] = set(int(u) for u in CFG.get("allowed_users", []))


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
def authorized(func):
    """Decorator: reject unknown users."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if ALLOWED_USERS and uid not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Unauthorized.")
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------
def run_cmd(args: list[str], timeout: int = 7200) -> tuple[bool, str]:
    """Run main.sh with given args. Returns (success, output)."""
    try:
        result = subprocess.run(
            ["bash", MAIN_SH] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SCRIPT_DIR,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, str(e)


def run_shell(cmd: str, timeout: int = 300) -> tuple[bool, str]:
    """Run arbitrary shell command."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, str(e)


def fmt(ok: bool, output: str) -> str:
    """Format shell output for Telegram (max 4000 chars)."""
    icon = "✅" if ok else "❌"
    text = f"{icon}\n<pre>{_escape(output)}</pre>" if output else icon
    return text[:4096]


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_long(update: Update, text: str):
    """Send a possibly-long HTML message, splitting if needed."""
    MAX = 4000
    if len(text) <= MAX:
        await update.message.reply_text(text, parse_mode="HTML")
        return
    # Split on newlines
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > MAX:
            await update.message.reply_text(chunk, parse_mode="HTML")
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
@authorized
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Income Node Runner — Bot Commands</b>\n\n"
        "<b>Nodes</b>\n"
        "  /nodes — list all nodes\n"
        "  /start_all — start all nodes\n"
        "  /stop_all — stop all nodes\n"
        "  /setup — setup nodes from proxies.txt\n"
        "  /start &lt;id&gt; [id2...] — start node(s)\n"
        "  /stop &lt;id&gt; [id2...] — stop node(s)\n"
        "  /delete &lt;id&gt; [id2...] — delete node(s)\n"
        "  /delete_all — delete ALL nodes\n"
        "  /restart_all — restart tất cả nodes\n"
        "  /restart &lt;id&gt; [id2...] — restart node(s) cụ thể\n\n"
        "<b>Proxies</b>\n"
        "  /add &lt;proxy&gt; — add proxy &amp; create node\n"
        "  /remove &lt;proxy&gt; — remove proxy &amp; node\n\n"
        "<b>Config</b>\n"
        "  /earnapp — collect earnapp links\n"
        "  /update_props — sync properties.conf to all nodes\n\n"
        "<b>Web Server</b>\n"
        "  /web_status — check web server\n"
        "  /web_start — start web server\n"
        "  /web_stop — stop web server\n\n"
        "<b>System</b>\n"
        "  /docker_ps — list docker containers\n"
        "  /help — this message"
    )
    await update.message.reply_text(text, parse_mode="HTML")


@authorized
async def cmd_nodes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Fetching nodes...")
    ok, out = run_cmd(["--list-nodes"], timeout=120)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_start_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Starting all nodes... (may take a while)")
    ok, out = run_cmd(["--start-all"])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Stopping all nodes...")
    ok, out = run_cmd(["--stop-all"])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_setup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Setting up nodes from proxies.txt...")
    ok, out = run_cmd(["--setup-node"])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_start_node(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ids = ctx.args
    if not ids:
        await update.message.reply_text("Usage: /start &lt;id&gt; [id2...]", parse_mode="HTML")
        return
    await update.message.reply_text(f"⏳ Starting node(s): {' '.join(ids)}")
    ok, out = run_cmd(["--start-node"] + ids)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_stop_node(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ids = ctx.args
    if not ids:
        await update.message.reply_text("Usage: /stop &lt;id&gt; [id2...]", parse_mode="HTML")
        return
    await update.message.reply_text(f"⏳ Stopping node(s): {' '.join(ids)}")
    ok, out = run_cmd(["--stop-node"] + ids)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_delete_node(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ids = ctx.args
    if not ids:
        await update.message.reply_text("Usage: /delete &lt;id&gt; [id2...]", parse_mode="HTML")
        return
    await update.message.reply_text(f"⏳ Deleting node(s): {' '.join(ids)}")
    ok, out = run_cmd(["--delete-node"] + ids)
    await send_long(update, fmt(ok, out))


# --- /delete_all with confirmation ---
@authorized
async def cmd_delete_all_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ <b>Xác nhận xoá TẤT CẢ nodes?</b>\n"
        "Gõ <code>YES</code> để xác nhận, hoặc /cancel để huỷ.",
        parse_mode="HTML",
    )
    return CONFIRM_DELETE_ALL


async def cmd_delete_all_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "YES":
        await update.message.reply_text("⏳ Deleting all nodes...")
        ok, out = run_cmd(["--delete-all"])
        await send_long(update, fmt(ok, out))
    else:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


@authorized
async def cmd_restart_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Restarting all nodes (stop → start)... (may take a while)")
    ok, out = run_cmd(["--restart-all"])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_restart_node(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ids = ctx.args
    if not ids:
        await update.message.reply_text("Usage: /restart &lt;id&gt; [id2...]", parse_mode="HTML")
        return
    await update.message.reply_text(f"⏳ Restarting node(s): {' '.join(ids)}")
    ok, out = run_cmd(["--restart-node"] + ids)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_add_proxy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /add &lt;proxy&gt;\nVí dụ: /add socks5://user:pass@1.2.3.4:1080",
            parse_mode="HTML",
        )
        return
    proxy = " ".join(ctx.args)
    await update.message.reply_text(f"⏳ Adding proxy...")
    ok, out = run_cmd(["--add-proxy", proxy])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_remove_proxy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /remove &lt;proxy&gt;",
            parse_mode="HTML",
        )
        return
    proxy = " ".join(ctx.args)
    await update.message.reply_text(f"⏳ Removing proxy...")
    ok, out = run_cmd(["--remove-proxy", proxy])
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_earnapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Collecting earnapp links...")
    ok, out = run_cmd(["--collect-earnapp"], timeout=300)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_update_props(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Updating properties.conf on all nodes...")
    ok, out = run_cmd(["--update-properties"], timeout=300)
    await send_long(update, fmt(ok, out))


@authorized
async def cmd_web_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ok, out = run_shell("pgrep -a python3 | grep 'web/server.py'")
    if ok and out:
        await update.message.reply_text(f"🟢 Web server is running:\n<pre>{_escape(out)}</pre>", parse_mode="HTML")
    else:
        await update.message.reply_text("🔴 Web server is NOT running.")


@authorized
async def cmd_web_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ok, out = run_shell(f"bash {START_SH} --background")
    await send_long(update, fmt(ok, out or "Web server started."))


@authorized
async def cmd_web_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ok, out = run_shell(f"bash {START_SH} --stop")
    await send_long(update, fmt(ok, out or "Web server stopped."))


@authorized
async def cmd_docker_ps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ok, out = run_shell("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'")
    await send_long(update, fmt(ok, out))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(7200)
        .write_timeout(7200)
        .pool_timeout(7200)
        .build()
    )

    # delete_all conversation
    delete_all_conv = ConversationHandler(
        entry_points=[CommandHandler("delete_all", cmd_delete_all_start)],
        states={
            CONFIRM_DELETE_ALL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_delete_all_confirm)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(delete_all_conv)
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("nodes", cmd_nodes))
    app.add_handler(CommandHandler("list", cmd_nodes))
    app.add_handler(CommandHandler("start_all", cmd_start_all))
    app.add_handler(CommandHandler("stop_all", cmd_stop_all))
    app.add_handler(CommandHandler("restart_all", cmd_restart_all))
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("start_node", cmd_start_node))
    app.add_handler(CommandHandler("stop_node", cmd_stop_node))
    app.add_handler(CommandHandler("restart", cmd_restart_node))
    app.add_handler(CommandHandler("delete", cmd_delete_node))
    app.add_handler(CommandHandler("add", cmd_add_proxy))
    app.add_handler(CommandHandler("remove", cmd_remove_proxy))
    app.add_handler(CommandHandler("earnapp", cmd_earnapp))
    app.add_handler(CommandHandler("update_props", cmd_update_props))
    app.add_handler(CommandHandler("web_status", cmd_web_status))
    app.add_handler(CommandHandler("web_start", cmd_web_start))
    app.add_handler(CommandHandler("web_stop", cmd_web_stop))
    app.add_handler(CommandHandler("docker_ps", cmd_docker_ps))

    logger.info("Bot started. Waiting for messages...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
