## Overview

性能評価の実験で使用する、客役とAIの会話データを収集・提供するためのAPIサーバー。


## Run

- Local: `127.0.0.1:8000/`
  `uvicorn main:app --reload`

- Railway
  `uvicorn main:app --host 0.0.0.0 --port $PORT`


## Json URL

`URL`: `/conversations?token={token}`
