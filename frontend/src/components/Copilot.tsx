import { useRef, useState } from "react";
import { Input, Button, Tag, Typography, Spin, Space } from "antd";
import { SendOutlined, ThunderboltOutlined, ExperimentOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useActiveTask } from "../state/taskContext";
import { useI18n } from "../i18n";
import type { Citation, CopilotMessage } from "../api/types";

const { Text } = Typography;

interface Turn {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  error?: boolean;
}

export default function Copilot() {
  const { activeTask } = useActiveTask();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const suggestions = [t("cp.sug1"), t("cp.sug2"), t("cp.sug3")];

  const send = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || loading) return;
    setInput("");
    const history: CopilotMessage[] = turns
      .filter((x) => !x.error)
      .slice(-6)
      .map((x) => ({ role: x.role, content: x.content }));
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setLoading(true);
    try {
      const reply = await api.copilotChat(message, activeTask?.task_id ?? null, history);
      setTurns((prev) => [...prev, { role: "assistant", content: reply.answer, citations: reply.citations }]);
    } catch (e) {
      const err = e as ApiError;
      const blocked = err.status === 403;
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          error: true,
          content: blocked ? t("cp.blocked", { msg: err.message }) : t("cp.failed", { msg: err.message }),
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }), 50);
    }
  };

  return (
    <>
      <div className="copilot-head">
        <div className="ch-title">
          <ThunderboltOutlined /> {t("cp.title")}
        </div>
        <div className="ch-sub">
          {activeTask
            ? t("cp.sub", {
                task: activeTask.task_id,
                dataset: activeTask.dataset_id ?? t("cp.noDataset"),
                r: activeTask.round,
                n: activeTask.rounds,
              })
            : t("cp.noTask")}
        </div>
      </div>

      <div className="copilot-body" ref={listRef}>
        {turns.length === 0 && (
          <>
            <div className="msg ai">
              <div className="av">DX</div>
              <div className="bubble">
                <div className="md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{t("cp.intro")}</ReactMarkdown>
                </div>
              </div>
            </div>
            <div>
              <div className="nav-group-label" style={{ paddingLeft: 0 }}>
                {t("cp.suggestions")}
              </div>
              <div className="chips">
                {suggestions.map((s) => (
                  <button className="chip small" key={s} onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {turns.map((turn, i) => (
          <div className={`msg ${turn.role === "user" ? "user" : "ai"}`} key={i}>
            <div className="av">{turn.role === "user" ? "You" : "DX"}</div>
            <div className="bubble" style={turn.error ? { color: "#f2707a" } : undefined}>
              {turn.role === "assistant" && !turn.error ? (
                <div className="md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
                </div>
              ) : (
                turn.content
              )}
              {turn.citations && turn.citations.length > 0 && (
                <div className="cite-line">
                  {t("cp.citations")}
                  {turn.citations.map((c) => (
                    <Tag key={c.id} color="cyan" style={{ marginInlineStart: 6 }}>
                      {c.id}
                    </Tag>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg ai">
            <div className="av">DX</div>
            <div className="bubble">
              <Spin size="small" /> <Text type="secondary">{t("cp.thinking")}</Text>
            </div>
          </div>
        )}

        {activeTask && (
          <div className="chips">
            <Button size="small" icon={<ExperimentOutlined />} onClick={() => navigate(`/tasks/${activeTask.task_id}`)}>
              {t("cp.taskDetail")}
            </Button>
          </div>
        )}
      </div>

      <div className="copilot-foot">
        <Space.Compact style={{ width: "100%" }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => send()}
            placeholder={t("cp.placeholder")}
            disabled={loading}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={() => send()} loading={loading} />
        </Space.Compact>
      </div>
    </>
  );
}
