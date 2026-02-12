"use client"

import React, { useEffect, useState } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Node as ReactFlowNode,
  Handle,
  Position,
  MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import GlobalConfigs from "@/app/app.config"

// Define type for edges
interface EdgeType {
    id: string;
    source: string;
    target: string;
    animated?: boolean;
    style?: React.CSSProperties;
    markerEnd?: {
      type: typeof MarkerType[keyof typeof MarkerType];
      width?: number;
      height?: number;
      color?: string;
    };
    type?: string;
}

// Define node type for backend topology data
interface TopologyNode {
  id: string;
  type: string;
  position?: { x: number; y: number };
  data?: {
    domainName?: string;
    domainControllerName?: string;
    workstationName?: string;
    caName?: string;
    privateIPAddress?: string;
    hasPublicIP?: boolean;
    isSub?: boolean;
  };
  domain?: string;
}

// Custom node components matching Build page style
const DomainControllerNode = ({ data }: { data: any }) => (
  <div
    className={`p-4 rounded-xl shadow-2xl relative border backdrop-blur-sm ${
      data.hasPublicIP ? "ring-2 ring-accent ring-offset-2 ring-offset-base-100" : ""
    } ${
      data.isSub
        ? "bg-gradient-to-br from-purple-600 to-violet-700 shadow-purple-900/50 border-purple-500/30"
        : "bg-gradient-to-br from-pink-600 to-rose-700 shadow-pink-900/50 border-pink-500/30"
    } text-white`}
  >
    {data.hasPublicIP && (
      <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
        Public IP
      </div>
    )}
    <strong className="text-sm font-bold">
      {data.isSub ? "Sub DC" : "Domain Controller"}
    </strong>
    <div className="text-xs mt-2 space-y-1">
      <div className="font-semibold">{data.domainControllerName}</div>
      <div className={data.isSub ? "text-purple-100" : "text-pink-100"}>
        {data.domainName}
      </div>
      <div className={data.isSub ? "text-purple-200" : "text-pink-200"}>
        IP: {data.privateIPAddress}
      </div>
    </div>
    <Handle
      type="source"
      position={Position.Right}
      id="source"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: data.isSub ? "2px solid #9333ea" : "2px solid #ec4899",
      }}
    />
    <Handle
      type="target"
      position={Position.Left}
      id="target"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: data.isSub ? "2px solid #9333ea" : "2px solid #ec4899",
      }}
    />
  </div>
);

const WorkstationNode = ({ data }: { data: any }) => (
  <div className={`bg-gradient-to-br from-emerald-600 to-teal-700 text-white p-4 rounded-xl shadow-2xl shadow-emerald-900/50 relative border border-emerald-500/30 backdrop-blur-sm ${
    data.hasPublicIP ? "ring-2 ring-accent ring-offset-2 ring-offset-base-100" : ""
  }`}>
    {data.hasPublicIP && (
      <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
        Public IP
      </div>
    )}
    <strong className="text-sm font-bold">Workstation</strong>
    <div className="text-xs mt-2 space-y-1">
      <div className="font-semibold">{data.workstationName}</div>
      <div className="text-emerald-100">{data.domainName || ""}</div>
      <div className="text-emerald-200">IP: {data.privateIPAddress}</div>
    </div>
    <Handle
      type="target"
      position={Position.Left}
      id="target"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: "2px solid #10b981",
      }}
    />
    <Handle
      type="source"
      position={Position.Right}
      id="source"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: "2px solid #10b981",
      }}
    />
  </div>
);

const JumpboxNode = ({ data }: { data: any }) => (
  <div className="bg-gradient-to-br from-orange-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-orange-900/50 relative border border-orange-400/30 backdrop-blur-sm">
    <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
      Public IP
    </div>
    <strong className="text-sm font-bold">Jumpbox</strong>
    <div className="text-xs mt-2">
      <div className="text-orange-100">IP: {data.privateIPAddress}</div>
    </div>
    <Handle
      type="source"
      position={Position.Right}
      id="source"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: "2px solid #f97316",
      }}
    />
    <Handle
      type="target"
      position={Position.Left}
      id="target"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: "2px solid #f97316",
      }}
    />
  </div>
);

const CertificateAuthorityNode = ({ data }: { data: any }) => (
  <div className={`bg-gradient-to-br from-yellow-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-yellow-900/50 relative border border-yellow-400/30 backdrop-blur-sm ${
    data.hasPublicIP ? "ring-2 ring-accent ring-offset-2 ring-offset-base-100" : ""
  }`}>
    {data.hasPublicIP && (
      <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
        Public IP
      </div>
    )}
    <strong className="text-sm font-bold">Certificate Authority</strong>
    <div className="text-xs mt-2 space-y-1">
      <div className="font-semibold">{data.caName}</div>
      <div className="text-yellow-100">{data.domainName || ""}</div>
      <div className="text-yellow-200">IP: {data.privateIPAddress}</div>
    </div>
    <Handle
      type="target"
      position={Position.Left}
      id="target"
      style={{
        background: "#fff",
        width: 12,
        height: 12,
        border: "2px solid #eab308",
      }}
    />
  </div>
);

// Register custom node types
const nodeTypes = {
  domainController: DomainControllerNode,
  workstation: WorkstationNode,
  jumpbox: JumpboxNode,
  certificateAuthority: CertificateAuthorityNode,
};

// Define node type for ReactFlow
interface CustomNodeData {
  id: string;
  type: string;
  data: any;
  position: { x: number; y: number };
}

// Override the default styles
const containerStyle = {
  height: 500, 
  width: '100%',
  background: 'transparent'
};

interface TopologyVisualizationProps {
  deploymentID?: string;
  scenarioName?: string;
}

const nodeWidth = 180;
const nodeHeight = 80;
const initialNodeSpacing = 250;
const verticalSpacing = 150;

const TopologyVisualization: React.FC<TopologyVisualizationProps> = ({ 
  deploymentID, 
  scenarioName 
}) => {
  // Update state types to match custom nodes
  const [nodes, setNodes] = useState<CustomNodeData[]>([]);
  const [edges, setEdges] = useState<EdgeType[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTopology = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const response = await fetch(GlobalConfigs.getTopologyEndpoint, {
          method: 'POST',
          body: JSON.stringify({ 
            deploymentID: deploymentID || '', 
            scenarioName: scenarioName || '' 
          }),
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (!response.ok) {
          throw new Error(`Failed to fetch topology: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.topology && data.topology.nodes) {
          
          // Simpler hierarchical LEFT-TO-RIGHT layout (matches BloodHoundImport)
          const spacing = { x: 280, y: 150 };
          const allNodes = [...data.topology.nodes] as TopologyNode[];
          
          // Build parent-child relationships from edges
          const childrenMap = new Map<string, string[]>();
          const hasParent = new Set<string>();
          
          data.topology.edges.forEach((edge: any) => {
            if (!childrenMap.has(edge.source)) {
              childrenMap.set(edge.source, []);
            }
            childrenMap.get(edge.source)!.push(edge.target);
            hasParent.add(edge.target);
          });
          
          // Find root nodes (no incoming edges) - these are root DCs
          const rootNodes = allNodes.filter((n) => 
            n.type === 'domainController' && !hasParent.has(n.id)
          );
          
          // Find jumpboxes
          const jumpboxes = allNodes.filter((n) => n.type === 'jumpbox');
          
          // Track all positioned node IDs
          const positionedIds = new Set<string>();
          
          // Recursive function to position children (defined before use)
          const positionChildrenRecursive = (parent: TopologyNode, depth: number) => {
            const childIds = childrenMap.get(parent.id) || [];
            const children = childIds
              .map((id) => allNodes.find((n) => n.id === id))
              .filter((n): n is TopologyNode => n !== undefined && !positionedIds.has(n.id));
            
            if (children.length === 0) return;
            
            const parentY = parent.position?.y || 100;
            
            // Position children to the right of parent, centered vertically around parent
            children.forEach((child, index) => {
              child.position = {
                x: (parent.position?.x || 100) + spacing.x,
                y: parentY - ((children.length - 1) * spacing.y) / 2 + index * spacing.y,
              };
              positionedIds.add(child.id);
              
              // Recursively position grandchildren
              positionChildrenRecursive(child, depth + 1);
            });
          };
          
          // Position root nodes on the left, stacked vertically with extra spacing
          rootNodes.forEach((root, index) => {
            root.position = { x: 100, y: 100 + index * spacing.y * 2 };
            positionedIds.add(root.id);
            positionChildrenRecursive(root, 1);
          });
          
          // Position jumpboxes at the far right
          const maxX = Math.max(...allNodes.filter(n => positionedIds.has(n.id)).map((n) => n.position?.x || 0), 100);
          jumpboxes.forEach((jumpbox, index) => {
            if (!positionedIds.has(jumpbox.id)) {
              jumpbox.position = { x: maxX + spacing.x, y: 100 + index * spacing.y };
              positionedIds.add(jumpbox.id);
            }
          });
          
          // Position any remaining unpositioned nodes (CAs, workstations not connected)
          const unpositioned = allNodes.filter(n => !positionedIds.has(n.id));
          if (unpositioned.length > 0) {
            const finalMaxX = Math.max(...allNodes.filter(n => positionedIds.has(n.id)).map((n) => n.position?.x || 0), 100);
            unpositioned.forEach((node, index) => {
              node.position = { x: finalMaxX + spacing.x, y: 100 + index * spacing.y };
              positionedIds.add(node.id);
            });
          }
          
          // Transform topology data to ReactFlow format using custom node types
          const reactFlowNodes = allNodes.map<CustomNodeData>((node) => {
            const nodeType = node.type || 'domainController';
            
            // Determine if this DC is a Sub DC by checking if it has a parent DC edge
            let isSub = false;
            if (nodeType === 'domainController') {
              const hasParentDC = data.topology.edges.some(edge => 
                edge.target === node.id && 
                data.topology.nodes.find(n => n.id === edge.source)?.type === 'domainController'
              );
              isSub = hasParentDC;
            }
            
            // Pass all node data to custom components
            return {
              id: node.id,
              type: nodeType,  // Use custom node types: domainController, workstation, jumpbox, certificateAuthority
              data: { 
                ...node.data,
                isSub,
                hasPublicIP: node.data?.hasPublicIP === true,
              },
              position: node.position || { x: 0, y: 0 },
            };
          });
          
          // Enhanced edges with better styling
          const reactFlowEdges = data.topology.edges.map((edge) => ({
            id: `${edge.source}-${edge.target}`,
            source: edge.source,
            target: edge.target,
            sourceHandle: edge.sourceHandle,
            targetHandle: edge.targetHandle,
            animated: true,
            style: { stroke: '#888', strokeWidth: 2 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 15,
              height: 15,
              color: '#888',
            },
            type: 'smoothstep', // Use smoothstep for nicer curves
          }));
          
          setNodes(reactFlowNodes);
          setEdges(reactFlowEdges);
        } else {
          setError("No topology data available in the response");
        }
      } catch (error) {
        console.error('Failed to fetch topology:', error);
        setError(error instanceof Error ? error.message : "Unknown error fetching topology");
      } finally {
        setLoading(false);
      }
    };
    
    if (scenarioName || deploymentID) {
      fetchTopology();
    } else {
      setLoading(false);
    }
  }, [deploymentID, scenarioName]);
  
  if (loading) return <div className="text-center">Loading topology...</div>;
  
  if (error) return <div className="text-center text-error">{error}</div>;
  
  if (nodes.length === 0) return <div className="text-center">No topology data available</div>;
  
  return (
    <div style={containerStyle} className="border border-base-300 rounded overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        defaultEdgeOptions={{
          type: 'smoothstep',
          style: { stroke: '#888', strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed },
        }}
      >
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  );
};

export default TopologyVisualization;