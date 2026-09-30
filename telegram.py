"""Integração Telegram: recebe mensagens, envia notificações e processa comandos."""
import os
import asyncio
import json
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from telegram.error import TelegramError
from .config import DATA

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USERS_FILE = DATA / "telegram_users.json"


class TelegramManager:
    """Gerencia a integração com Telegram."""

    def __init__(self):
        self.app: Application | None = None
        self.bot: Bot | None = None
        self.hub = None
        self.on_message = None  # callback para processar mensagens
        self.user_mapping = self._load_user_mapping()

    def _load_user_mapping(self) -> dict:
        """Carrega mapeamento de usuários Telegram (chat_id -> nome/info)."""
        if TELEGRAM_USERS_FILE.exists():
            return json.loads(TELEGRAM_USERS_FILE.read_text())
        return {}

    def _save_user_mapping(self):
        """Salva mapeamento de usuários."""
        TELEGRAM_USERS_FILE.write_text(json.dumps(self.user_mapping, indent=2))

    async def initialize(self):
        """Inicializa o bot do Telegram."""
        if not TELEGRAM_BOT_TOKEN:
            print("⚠️  TELEGRAM_BOT_TOKEN não configurado, pulando inicialização")
            return

        try:
            self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
            self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

            # Adiciona handlers
            self.app.add_handler(CommandHandler("start", self._handle_start))
            self.app.add_handler(CommandHandler("help", self._handle_help))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

            print("✅ Telegram bot inicializado")
        except Exception as e:
            print(f"❌ Erro ao inicializar Telegram: {e}")
            self.bot = None
            self.app = None

    async def start(self):
        """Inicia o bot com polling."""
        if not self.app:
            return
        try:
            await self.app.initialize()
            await self.app.start()
            print("🚀 Telegram bot iniciado com polling")
        except Exception as e:
            print(f"❌ Erro ao iniciar Telegram polling: {e}")

    async def stop(self):
        """Para o bot."""
        if not self.app:
            return
        try:
            await self.app.stop()
            await self.app.shutdown()
            print("⏹️  Telegram bot parado")
        except Exception as e:
            print(f"❌ Erro ao parar Telegram: {e}")

    # -------- Handlers --------
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler do comando /start."""
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name or "Usuário"

        # Registra o usuário
        self.user_mapping[str(chat_id)] = {
            "name": user_name,
            "username": update.effective_user.username,
            "first_seen": str(update.message.date)
        }
        self._save_user_mapping()

        await update.message.reply_text(
            f"👋 Olá {user_name}! Sou o SIMBA, seu assistente pessoal.\n\n"
            f"Envie mensagens e vou processar seus pedidos. "
            f"Use /help para ver os comandos disponíveis."
        )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler do comando /help."""
        help_text = """
📋 Comandos disponíveis:
/start - Iniciar conversa
/help - Mostrar esta mensagem

💬 Envie qualquer mensagem de texto e o SIMBA irá:
• Processar seus pedidos
• Responder às suas perguntas
• Executar ações (com sua aprovação)
• Enviar notificações quando necessário
        """
        await update.message.reply_text(help_text.strip())

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para mensagens de texto."""
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name or "Telegram"
        text = update.message.text

        # Registra o usuário se novo
        if str(chat_id) not in self.user_mapping:
            self.user_mapping[str(chat_id)] = {
                "name": user_name,
                "username": update.effective_user.username,
                "first_seen": str(update.message.date)
            }
            self._save_user_mapping()

        # Processa a mensagem via callback
        if self.on_message:
            try:
                await self.on_message({
                    "text": text,
                    "origin": "telegram",
                    "chat_id": chat_id,
                    "user_name": user_name
                })
            except Exception as e:
                print(f"❌ Erro ao processar mensagem Telegram: {e}")
                await update.message.reply_text(f"❌ Erro ao processar: {str(e)[:100]}")

    # -------- Envio de mensagens --------
    async def send_message(self, chat_id: int | str, text: str):
        """Envia uma mensagem para um chat do Telegram."""
        if not self.bot:
            return False
        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            return True
        except TelegramError as e:
            print(f"❌ Erro ao enviar mensagem Telegram: {e}")
            return False

    async def send_to_all_users(self, text: str):
        """Envia notificação para todos os usuários Telegram registrados."""
        if not self.bot:
            return

        sent = 0
        for chat_id in self.user_mapping.keys():
            try:
                await self.bot.send_message(chat_id=int(chat_id), text=text)
                sent += 1
            except TelegramError as e:
                print(f"⚠️  Erro ao enviar para {chat_id}: {e}")
            except Exception as e:
                print(f"⚠️  Erro inesperado para {chat_id}: {e}")

        if sent > 0:
            print(f"✅ Notificação enviada para {sent} usuários Telegram")

    def get_users(self) -> list[int]:
        """Retorna lista de chat IDs dos usuários registrados."""
        return [int(cid) for cid in self.user_mapping.keys()]

    def user_count(self) -> int:
        """Retorna número de usuários registrados."""
        return len(self.user_mapping)


# Instância global
telegram: TelegramManager | None = None


def get_telegram() -> TelegramManager:
    """Obtém ou cria a instância global do Telegram."""
    global telegram
    if telegram is None:
        telegram = TelegramManager()
    return telegram


async def send_telegram_notification(text: str):
    """Envia notificação para todos os usuários Telegram."""
    tm = get_telegram()
    if tm:
        await tm.send_to_all_users(text)
