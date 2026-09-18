import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CheckOutlined } from "@ant-design/icons";
import { useI18n } from "../i18n";

export type StageState = "done" | "running" | "pending";

interface NodeData extends Record<string, unknown> {
  title: string;
  sub: string;
  state: StageState;
  step: number;
}

/** Circular status marker: green check when done, pulsing ring while running. */
function StatusBadge({ state }: { state: StageState }) {
  return (
    <span className={`n-badge ${state}`} aria-hidden="true">
      {state === "done" ? <CheckOutlined /> : state === "running" ? <span className="n-badge-dot" /> : null}
    </span>
  );
}

function DmtaNode({ data }: { data: NodeData }) {
  return (
    <div className={`dx-node ${data.state}`}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle id="loop-in" type="target" position={Position.Bottom} style={{ opacity: 0 }} />
      <div className="n-head">
        <StatusBadge state={data.state} />
        <span className="n-step">{String(data.step).padStart(2, "0")}</span>
      </div>
      <div className="n-title">{data.title}</div>
      <div className="n-sub">{data.sub}</div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
      <Handle id="loop-out" type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

/** The analyse -> design feedback loop, labelled with a circular "迭代" badge. */
function IterationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  animated,
}: EdgeProps) {
  const { t } = useI18n();
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 20,
  });
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          className={`iter-badge${animated ? " active" : ""}`}
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "none",
          }}
        >
          {t("detail.iteration")}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = { dmta: DmtaNode };
const edgeTypes = { iteration: IterationEdge };

export default function DmtaFlow({ stage, status }: { stage: string; status: string }) {
  const { t } = useI18n();
  const stages = [
    { key: "target", title: t("stage.target"), sub: t("detail.agentTarget") },
    { key: "design", title: t("stage.design"), sub: t("detail.agentDesign") },
    { key: "make", title: t("stage.make"), sub: t("detail.agentMake") },
    { key: "test", title: t("stage.test"), sub: t("detail.agentTest") },
    { key: "analyze", title: t("stage.analyze"), sub: t("detail.agentAnalyze") },
  ];

  const order = stages.findIndex((s) => s.key === stage);
  const done = status === "succeeded";

  const nodes: Node<NodeData>[] = stages.map((s, i) => {
    let state: StageState = "pending";
    if (done) state = "done";
    else if (order === -1) state = "pending";
    else if (i < order) state = "done";
    else if (i === order) state = "running";
    return {
      id: s.key,
      type: "dmta",
      position: { x: i * 196, y: 70 },
      data: { title: s.title, sub: s.sub, state, step: i + 1 },
    };
  });

  const edges: Edge[] = [
    { id: "e1", source: "target", target: "design", markerEnd: { type: MarkerType.ArrowClosed }, animated: order === 1 },
    { id: "e2", source: "design", target: "make", markerEnd: { type: MarkerType.ArrowClosed }, animated: order === 2 },
    { id: "e3", source: "make", target: "test", markerEnd: { type: MarkerType.ArrowClosed }, animated: order === 3 },
    { id: "e4", source: "test", target: "analyze", markerEnd: { type: MarkerType.ArrowClosed }, animated: order === 4 },
    {
      id: "e5",
      source: "analyze",
      sourceHandle: "loop-out",
      target: "design",
      targetHandle: "loop-in",
      type: "iteration",
      animated: status === "running",
      style: { strokeDasharray: "5 5" },
      markerEnd: { type: MarkerType.ArrowClosed },
    },
  ];

  return (
    <div className="dx-flow">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        nodesDraggable={false}
      >
        <Background color="#1e2b42" gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
