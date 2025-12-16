import gspread
from google.oauth2.service_account import Credentials
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


def save_row_to_sheet(name: str, user_utts: list[str], ai_uttis: list[str]):
    creds_info = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    gc = gspread.authorize(creds)
    sheet = gc.open_by_key("1cbeBpGD7h5uBd4lH4ggU5srKvo01kAhXNpnupw-zGXQ").sheet1

    sheet.append_row(
        [
            datetime.now().isoformat(),
            "\n".join(user_utts),
            "\n".join(ai_uttis),
        ]
    )


save_row_to_sheet("test1", ["hello", "world"], ["panda", "penguin"])
save_row_to_sheet("test2", ["hello", "world"], ["panda", "penguin"])
# https://docs.google.com/spreadsheets/d/1cbeBpGD7h5uBd4lH4ggU5srKvo01kAhXNpnupw-zGXQ/edit?usp=sharing
