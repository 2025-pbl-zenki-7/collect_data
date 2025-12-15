## Overview

性能評価の実験で使用する、客役とAIの会話データを収集・提供するためのAPIサーバー。
Railway上で、FastAPIを用いて構築している。


## Access

- Base URL: [pbl-collect-data.mtaisei.com](pbl-collect-data.mtaisei.com)


## Run

- Local: `127.0.0.1:8000/`
  `uvicorn main:app --reload`

- Railway
  `uvicorn main:app --host 0.0.0.0 --port $PORT`


## Json URL

`URL`: `https://pbl-collect-data.mtaisei.com/conversations?token={token}`
