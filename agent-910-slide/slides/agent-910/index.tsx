import type { CSSProperties, ReactNode } from 'react';
import type { Page, SlideMeta } from '@open-slide/core';

const C = {
  bg: '#101418',
  panel: '#172027',
  panel2: '#202b33',
  text: '#f5f7fa',
  muted: '#aab8c2',
  cyan: '#36c7d0',
  green: '#71d17c',
  yellow: '#f1c95b',
  red: '#ff7a70',
  line: '#33434e',
  white: '#ffffff',
};

const base: CSSProperties = {
  width: '100%',
  height: '100%',
  boxSizing: 'border-box',
  background: C.bg,
  color: C.text,
  fontFamily:
    '"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", Inter, system-ui, sans-serif',
  position: 'relative',
  overflow: 'hidden',
};

function Slide({
  children,
  eyebrow = 'Agent-910',
  page,
}: {
  children: ReactNode;
  eyebrow?: string;
  page?: string;
}) {
  return (
    <section style={{ ...base, padding: '82px 104px' }}>
      <div style={gridBg} />
      <div style={topBar}>
        <span style={eyebrowStyle}>{eyebrow}</span>
        <span style={pageStyle}>{page}</span>
      </div>
      <div style={{ position: 'relative', zIndex: 1, height: '100%' }}>{children}</div>
    </section>
  );
}

function Title({ children, size = 84 }: { children: ReactNode; size?: number }) {
  return (
    <h1
      style={{
        fontSize: size,
        lineHeight: 1.05,
        margin: 0,
        color: C.text,
        fontWeight: 850,
      }}
    >
      {children}
    </h1>
  );
}

function Subtitle({ children }: { children: ReactNode }) {
  return (
    <p style={{ fontSize: 34, lineHeight: 1.55, margin: '28px 0 0', color: C.muted }}>
      {children}
    </p>
  );
}

function Pill({ children, color = C.cyan }: { children: ReactNode; color?: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        border: `2px solid ${color}`,
        color,
        borderRadius: 999,
        padding: '12px 24px',
        fontSize: 24,
        fontWeight: 700,
      }}
    >
      {children}
    </span>
  );
}

function Card({
  children,
  accent = C.cyan,
  style,
}: {
  children: ReactNode;
  accent?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        background: C.panel,
        border: `1px solid ${C.line}`,
        borderTop: `8px solid ${accent}`,
        borderRadius: 18,
        padding: 34,
        boxShadow: '0 18px 60px rgba(0, 0, 0, 0.28)',
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '34px 0 0' }}>
      {items.map((item, i) => (
        <li
          key={i}
          style={{
            display: 'flex',
            gap: 22,
            alignItems: 'flex-start',
            fontSize: 34,
            lineHeight: 1.45,
            marginBottom: 22,
            color: C.text,
          }}
        >
          <span
            style={{
              width: 18,
              height: 18,
              marginTop: 16,
              flex: '0 0 auto',
              borderRadius: 999,
              background: [C.cyan, C.green, C.yellow, C.red][i % 4],
            }}
          />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function CodeBlock({ children }: { children: ReactNode }) {
  return (
    <pre
      style={{
        margin: '34px 0 0',
        padding: '30px 34px',
        background: '#0b0f13',
        border: `1px solid ${C.line}`,
        borderRadius: 16,
        fontSize: 28,
        lineHeight: 1.55,
        color: C.green,
        whiteSpace: 'pre-wrap',
      }}
    >
      {children}
    </pre>
  );
}

function Split({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40, marginTop: 44 }}>
      <div>{left}</div>
      <div>{right}</div>
    </div>
  );
}

function SmallTitle({ children }: { children: ReactNode }) {
  return <h2 style={{ fontSize: 42, margin: 0, lineHeight: 1.15 }}>{children}</h2>;
}

function Flow({ steps }: { steps: string[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 18, marginTop: 50 }}>
      {steps.map((step, i) => (
        <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <Card accent={[C.cyan, C.green, C.yellow][i % 3]} style={{ minHeight: 250, padding: 24 }}>
            <div style={{ color: C.muted, fontSize: 24, marginBottom: 18 }}>
              STEP {String(i + 1).padStart(2, '0')}
            </div>
            <div style={{ fontSize: 29, lineHeight: 1.32, fontWeight: 800 }}>{step}</div>
          </Card>
        </div>
      ))}
    </div>
  );
}

const gridBg: CSSProperties = {
  position: 'absolute',
  inset: 0,
  backgroundImage:
    'linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)',
  backgroundSize: '64px 64px',
  opacity: 0.65,
};

const topBar: CSSProperties = {
  position: 'absolute',
  top: 38,
  left: 104,
  right: 104,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  zIndex: 2,
};

const eyebrowStyle: CSSProperties = {
  fontSize: 22,
  color: C.cyan,
  fontWeight: 850,
  letterSpacing: 1.5,
  textTransform: 'uppercase',
};

const pageStyle: CSSProperties = {
  fontSize: 20,
  color: C.muted,
  fontWeight: 700,
};

const Cover: Page = () => (
  <Slide page="01">
    <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
      <div style={{ textAlign: 'center', maxWidth: 1350 }}>
        <Pill>Discord 智慧會議助理</Pill>
        <Title size={140}>Agent-910</Title>
        <Subtitle>
          把聊天、排時間、語音會議紀錄與 Google Calendar 邀請整合在同一個 Discord bot。
        </Subtitle>
        <div style={{ marginTop: 50, color: C.muted, fontSize: 28 }}>
          github.com/User-Howard/Agent-910
        </div>
      </div>
    </div>
  </Slide>
);

const Motivation: Page = () => (
  <Slide page="02">
    <Title>專案動機</Title>
    <Subtitle>多人在 Discord 討論會議時，最常卡在三個地方。</Subtitle>
    <Split
      left={
        <Bullets
          items={[
            '訊息太多，前面講過的時間容易被忘記',
            '大家可用時間不一致，人工比對很麻煩',
            '確定時間後，還要手動建立 Google Calendar 活動',
          ]}
        />
      }
      right={
        <Card accent={C.green}>
          <SmallTitle>Agent-910 的目標</SmallTitle>
          <p style={{ fontSize: 36, lineHeight: 1.55, color: C.text, marginTop: 30 }}>
            讓會議流程直接發生在 Discord 對話裡，從找時間到建立行事曆邀請一次完成。
          </p>
        </Card>
      }
    />
  </Slide>
);

const Goals: Page = () => (
  <Slide page="03">
    <Title>專案目標</Title>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 28, marginTop: 58 }}>
      {[
        ['自然聊天', '在 Discord 頻道中回應使用者需求', C.cyan],
        ['理解脈絡', '讀取前面訊息並找出會議資訊', C.green],
        ['多人排程', '整理可用時間並計算重疊時段', C.yellow],
        ['語音統整', '錄音、轉錄並產生會議摘要', C.red],
        ['Calendar API', '建立 Google Calendar 活動', C.cyan],
        ['寄送邀請', '邀請已登記的 Google Calendar email', C.green],
      ].map(([title, body, color]) => (
        <Card key={title} accent={color} style={{ minHeight: 210 }}>
          <h2 style={{ fontSize: 42, margin: 0 }}>{title}</h2>
          <p style={{ fontSize: 28, lineHeight: 1.45, color: C.muted }}>{body}</p>
        </Card>
      ))}
    </div>
  </Slide>
);

const Tech: Page = () => (
  <Slide page="04">
    <Title>使用技術</Title>
    <Split
      left={
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginTop: 42 }}>
          {['Python', 'discord.py', 'pydantic-ai', 'SQLite', 'Google Calendar API', 'Docker', 'ffmpeg', 'libopus'].map(
            (item, i) => (
              <Pill key={item} color={[C.cyan, C.green, C.yellow, C.red][i % 4]}>
                {item}
              </Pill>
            ),
          )}
        </div>
      }
      right={
        <Card accent={C.yellow}>
          <SmallTitle>核心設計</SmallTitle>
          <p style={{ fontSize: 36, lineHeight: 1.55, color: C.text }}>
            LLM 負責理解自然語言；程式邏輯負責記憶、計算、錄音與 API 串接。
          </p>
        </Card>
      }
    />
  </Slide>
);

const Architecture: Page = () => (
  <Slide page="05">
    <Title>系統架構</Title>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24, marginTop: 44 }}>
      {[
        ['app/bot.py', 'Discord bot 入口、slash commands、訊息事件'],
        ['app/agent.py', 'LLM agent、聊天與排時間工具'],
        ['app/history.py', '讀取 Discord 前面訊息'],
        ['app/availability.py', 'SQLite 儲存可用時間並計算重疊'],
        ['app/recording.py', '語音會議錄音'],
        ['app/google_calendar.py', 'Google Calendar API 串接'],
        ['app/users.py', '使用者 Google Calendar email 資料庫'],
        ['app/calendar_delivery.py', '共用 Calendar invite 與 .ics 產生流程'],
      ].map(([file, desc], i) => (
        <Card key={file} accent={[C.cyan, C.green, C.yellow, C.red][i % 4]} style={{ padding: 24 }}>
          <div style={{ fontSize: 30, color: C.text, fontWeight: 850 }}>{file}</div>
          <div style={{ fontSize: 25, color: C.muted, marginTop: 12 }}>{desc}</div>
        </Card>
      ))}
    </div>
  </Slide>
);

const Scheduling: Page = () => (
  <Slide page="06">
    <Title>排時間功能</Title>
    <CodeBlock>@Agent-910 我們要找時間開會，Alice 和 Bob 也要來</CodeBlock>
    <Bullets
      items={[
        '讀取近期訊息',
        '抽取每個人的可用時間',
        '存入 SQLite',
        '計算重疊時段',
        '產生候選時間按鈕',
      ]}
    />
  </Slide>
);

const HistoryTool: Page = () => (
  <Slide page="07">
    <Title>看前面訊息 Tool</Title>
    <Subtitle>`read_more_messages` 讓 agent 在資訊不足時往前讀更多 Discord 訊息。</Subtitle>
    <Split
      left={<Bullets items={['找出會議參與者', '補上前面已經說過的可用時間', '避免只根據最新訊息做錯判斷']} />}
      right={
        <Card accent={C.cyan}>
          <SmallTitle>設計價值</SmallTitle>
          <p style={{ fontSize: 36, lineHeight: 1.55, color: C.text }}>
            bot 不只是回覆當下訊息，而是能理解整段對話脈絡。
          </p>
        </Card>
      }
    />
  </Slide>
);

const Calendar: Page = () => (
  <Slide page="08">
    <Title>會議確認與 Calendar</Title>
    <Bullets
      items={[
        '將會議標記為 settled',
        '建立 .ics 檔案作為備援',
        '若 Google OAuth 設定完成，建立 Google Calendar 活動',
        '邀請已登記的 Google Calendar email',
      ]}
    />
    <CodeBlock>{`/gmail name@company.edu.tw
/mygmail
/forgetgmail
/test_google_calendar_api`}</CodeBlock>
  </Slide>
);

const Voice: Page = () => (
  <Slide page="09">
    <Title>語音會議統整</Title>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 26, marginTop: 58 }}>
      {[
        ['/record', '加入語音頻道並開始錄音', C.red],
        ['/stop', '停止錄音並上傳 meeting.mp3', C.yellow],
        ['轉錄', '依說話者音訊產生文字稿', C.cyan],
        ['摘要', '整理重點、決議與 action items', C.green],
      ].map(([title, body, color]) => (
        <Card key={title} accent={color} style={{ minHeight: 300 }}>
          <div style={{ fontSize: 48, fontWeight: 900 }}>{title}</div>
          <p style={{ fontSize: 30, lineHeight: 1.45, color: C.muted }}>{body}</p>
        </Card>
      ))}
    </div>
  </Slide>
);

const Demo: Page = () => (
  <Slide page="10">
    <Title>Demo 流程</Title>
    <Flow
      steps={[
        '提出會議需求',
        '輸入可用時間',
        '整理可用時段',
        '顯示候選按鈕',
        '點選確認時間',
        '建立 Calendar 活動',
        '錄音與會後統整',
      ]}
    />
  </Slide>
);

const WorkSplit: Page = () => (
  <Slide page="11">
    <Title>分工比例</Title>
    <Subtitle>三位成員各負責 33%。</Subtitle>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 30, marginTop: 60 }}>
      {[
        ['吳浩瑋', '聊天功能、排時間 tool、看前面訊息 tool', C.cyan],
        ['蔡雨翰', '語音會議室錄音與會議統整', C.green],
        ['蔡俊則', '串接 Google Calendar API、建立活動、邀請 Gmail / Google Calendar email', C.yellow],
      ].map(([name, task, color]) => (
        <Card key={name} accent={color} style={{ minHeight: 420 }}>
          <div style={{ fontSize: 54, fontWeight: 900 }}>{name}</div>
          <div style={{ fontSize: 90, color, fontWeight: 950, marginTop: 18 }}>33%</div>
          <p style={{ fontSize: 30, lineHeight: 1.45, color: C.muted }}>{task}</p>
        </Card>
      ))}
    </div>
  </Slide>
);

const Howard: Page = () => (
  <Slide page="12">
    <Title>吳浩瑋負責部分</Title>
    <Bullets
      items={[
        'Discord 文字聊天互動',
        '使用 pydantic-ai 建立 agent',
        '判斷使用者是否想排會議',
        '建立排時間 tool',
        '建立讀取前面訊息 tool',
      ]}
    />
    <Subtitle>重點：把聊天內容轉成可計算的會議資料。</Subtitle>
  </Slide>
);

const VoiceOwner: Page = () => (
  <Slide page="13">
    <Title>蔡雨翰負責部分</Title>
    <Bullets
      items={['語音頻道錄音', '/record 與 /stop 指令', '混音並輸出 meeting.mp3', '語音轉文字', '產生會議摘要與 action items']}
    />
    <Subtitle>重點：讓 Discord 語音會議結束後，自動產生可閱讀的會議紀錄。</Subtitle>
  </Slide>
);

const CalendarOwner: Page = () => (
  <Slide page="14">
    <Title>蔡俊則負責部分</Title>
    <Bullets
      items={[
        'Google OAuth 設定',
        'Google Calendar API 串接',
        '建立 Calendar event',
        '邀請已登記 email 的參與者',
        '/gmail 與 /test_google_calendar_api 等測試指令',
      ]}
    />
    <Subtitle>重點：讓會議確認後不只停留在 Discord，而是能真正進入 Google Calendar。</Subtitle>
  </Slide>
);

const Features: Page = () => (
  <Slide page="15">
    <Title>專案特色</Title>
    <Bullets
      items={[
        '使用者不需要填表單，直接在 Discord 聊天即可',
        'bot 能記住前面訊息與每個人的回覆',
        '用 SQLite 保留會議狀態，重啟後資料仍存在',
        '語音會議可以自動轉成摘要',
        '確認時間後可直接建立 Google Calendar 活動',
      ]}
    />
  </Slide>
);

const Challenges: Page = () => (
  <Slide page="16">
    <Title>遇到的挑戰</Title>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 28, marginTop: 48 }}>
      {['中文自然語言時間解析', 'Discord 訊息脈絡判斷', '多人可用時間重疊計算', '語音錄製與不同說話者音訊處理', 'Google OAuth refresh token 與 Calendar API 權限設定'].map(
        (item, i) => (
          <Card key={item} accent={[C.red, C.yellow, C.cyan, C.green][i % 4]} style={{ minHeight: 150 }}>
            <div style={{ fontSize: 34, lineHeight: 1.35, fontWeight: 850 }}>{item}</div>
          </Card>
        ),
      )}
    </div>
  </Slide>
);

const Conclusion: Page = () => (
  <Slide page="17">
    <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
      <div style={{ maxWidth: 1350, textAlign: 'center' }}>
        <Title size={98}>讓 Discord 成為會議協作入口</Title>
        <Subtitle>
          會前排時間、會中錄音、會後統整、確認後建立 Google Calendar 活動並邀請參與者。
        </Subtitle>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 18, marginTop: 54 }}>
          <Pill color={C.cyan}>聊天中排時間</Pill>
          <Pill color={C.green}>語音會議統整</Pill>
          <Pill color={C.yellow}>Calendar 邀請</Pill>
        </div>
      </div>
    </div>
  </Slide>
);

export const meta: SlideMeta = {
  title: 'Agent-910',
};

export default [
  Cover,
  Motivation,
  Goals,
  Tech,
  Architecture,
  Scheduling,
  HistoryTool,
  Calendar,
  Voice,
  Demo,
  WorkSplit,
  Howard,
  VoiceOwner,
  CalendarOwner,
  Features,
  Challenges,
  Conclusion,
] satisfies Page[];
