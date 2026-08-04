# Agent-910

Discord 智慧會議助理

GitHub: https://github.com/User-Howard/Agent-910.git

---

# 專案動機

多人在 Discord 討論會議時，常遇到三個問題：

- 訊息太多，前面講過的時間容易被忘記
- 大家可用時間不一致，人工比對很麻煩
- 確定時間後，還要手動建立 Google Calendar 活動

Agent-910 的目標是把「聊天、排時間、會議紀錄、行事曆邀請」整合在同一個 Discord bot 裡。

---

# 專案目標

Agent-910 是一個 Discord bot agent，主要功能包含：

- 在 Discord 頻道中自然聊天
- 讀取前面訊息，理解使用者需求
- 協助多人排會議時間
- 記錄語音會議並產生統整
- 串接 Google Calendar API 建立活動
- 邀請已登記的 Google Calendar email

---

# 使用技術

- Python
- discord.py
- pydantic-ai
- SQLite
- Google Calendar API
- Docker / Docker Compose
- ffmpeg / libopus

核心設計：  
讓 LLM 負責理解自然語言，讓程式邏輯負責記憶、計算與 API 串接。

---

# 系統架構

主要模組：

- `app/bot.py`: Discord bot 入口、slash commands、訊息事件
- `app/agent.py`: LLM agent、聊天與排時間工具
- `app/history.py`: 讀取 Discord 前面訊息
- `app/availability.py`: SQLite 儲存可用時間並計算重疊
- `app/recording.py`: 語音會議錄音
- `app/google_calendar.py`: Google Calendar API 串接
- `app/users.py`: 使用者 Google Calendar email 資料庫

---

# 排時間功能

使用者只需要在 Discord 中標註 bot，例如：

```text
@Agent-910 我們要找時間開會，Alice 和 Bob 也要來
```

大家在聊天室中回覆可用時間後，bot 會：

- 讀取近期訊息
- 抽取每個人的可用時間
- 存入 SQLite
- 計算重疊時段
- 產生候選時間按鈕

---

# 看前面訊息 Tool

`read_more_messages` tool 讓 agent 可以在資訊不足時往前讀更多 Discord 訊息。

用途：

- 找出會議參與者
- 補上前面已經說過的可用時間
- 避免只根據最新訊息做錯判斷

這讓 bot 不只是回覆當下訊息，而是能理解整段對話脈絡。

---

# 會議確認與 Calendar

當時間確認後，Agent-910 會：

- 將會議標記為 settled
- 建立 `.ics` 檔案作為備援
- 若 Google OAuth 設定完成，建立 Google Calendar 活動
- 邀請已登記的 Google Calendar email

使用者可以用 slash command 管理 email：

```text
/gmail name@company.edu.tw
/mygmail
/forgetgmail
/test_google_calendar_api
```

---

# 語音會議統整

語音功能提供：

- `/record`: 加入目前語音頻道並開始錄音
- `/stop`: 停止錄音，上傳混音後的 `meeting.mp3`
- 對每位說話者音訊進行轉錄
- 產生會議摘要、重點、決議與 action items

這讓 Discord 語音會議結束後，可以直接拿到整理後的文字紀錄。

---

# Demo 流程

1. 使用者在 Discord mention bot，提出會議需求
2. 參與者輸入自己的可用時間
3. bot 讀取對話並整理可用時段
4. bot 顯示重疊時間與候選按鈕
5. 使用者點選確認時間
6. bot 建立 Google Calendar 活動並寄出邀請
7. 若是語音會議，可用 `/record` 和 `/stop` 產生會議統整

---

# 分工

三位成員各負責 33%：

| 成員 | 負責內容 | 比例 |
|---|---|---|
| 吳浩瑋 | 聊天功能、排時間 tool、看前面訊息 tool | 33% |
| 蔡雨翰 | 語音會議室錄音與會議統整 | 33% |
| 蔡俊則 | 串接 Google Calendar API、建立活動、邀請 Gmail / Google Calendar email | 33% |

---

# 吳浩瑋負責部分

主要功能：

- Discord 文字聊天互動
- 使用 pydantic-ai 建立 agent
- 判斷使用者是否想排會議
- 建立排時間 tool
- 建立讀取前面訊息 tool

重點：  
讓 bot 可以理解自然語言，並把聊天內容轉成可計算的會議資料。

---

# 蔡雨翰負責部分

主要功能：

- 語音頻道錄音
- `/record` 與 `/stop` 指令
- 混音並輸出 `meeting.mp3`
- 語音轉文字
- 產生會議摘要與 action items

重點：  
讓 Discord 語音會議結束後，可以自動產生可閱讀的會議紀錄。

---

# 蔡俊則負責部分

主要功能：

- Google OAuth 設定
- Google Calendar API 串接
- 建立 Calendar event
- 邀請已登記 email 的參與者
- `/gmail` 與 `/test_google_calendar_api` 等測試指令

重點：  
讓會議確認後不只停留在 Discord，而是能真正進入 Google Calendar。

---

# 專案特色

- 使用者不需要填表單，直接在 Discord 聊天即可
- bot 能記住前面訊息與每個人的回覆
- 用 SQLite 保留會議狀態，重啟後資料仍存在
- 語音會議可以自動轉成摘要
- 確認時間後可直接建立 Google Calendar 活動

---

# 遇到的挑戰

- 中文自然語言時間解析
- Discord 訊息脈絡判斷
- 多人可用時間重疊計算
- 語音錄製與不同說話者音訊處理
- Google OAuth refresh token 與 Calendar API 權限設定

---

# 結論

Agent-910 把 Discord 中常見的會議流程自動化：

- 會前：聊天中排時間
- 會中：語音會議錄音
- 會後：自動統整紀錄
- 確認後：建立 Google Calendar 活動並邀請參與者

它讓 Discord 不只是聊天工具，也能成為團隊協作與會議管理的入口。
