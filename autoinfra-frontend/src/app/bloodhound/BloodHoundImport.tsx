"use client"
import React, { useState, useCallback, useEffect } from "react"
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  useEdgesState,
  useNodesState,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type Connection,
} from "reactflow"
import "reactflow/dist/style.css"
import GlobalConfigs from "@/app/app.config"
import { SetCookie } from "@/components/cookieHandler"

// ============================================================================
// TYPES
// ============================================================================

interface DomainInfo {
  name: string
  sid: string
  functional_level: string | null
  lockout_threshold: number
  machine_account_quota: number
}

interface UploadSummary {
  total_computers: number
  domain_controllers: number
  workstations: number
  total_users: number
  enabled_users: number
}

interface AttackPaths {
  asrep_roastable: string[]
  kerberoastable: string[]
  unconstrained_delegation: string[]
  constrained_delegation_count: number
  acl_attack_paths_count: number
}

interface UploadResult {
  success: boolean
  upload_id: string
  domain: DomainInfo
  summary: UploadSummary
  attack_paths: AttackPaths
}

interface GenerateResult {
  success: boolean
  scenario_name: string
  topology: {
    nodes: any[]
    edges: any[]
  }
  users_to_create: Array<{
    username: string
    password: string
    attacks?: Array<{ type: string; description: string }>
  }>
  attacks_to_enable: Array<{
    attack_type: string
    target_user: string
  }>
}

interface DeploymentItem {
  name: string
  status: "running" | "succeeded" | "failed" | "pending"
}

interface ConfigurationStep {
  name: string
  status: "pending" | "running" | "succeeded" | "failed"
  message?: string
}

type Step = "upload" | "preview" | "topology" | "deploying" | "configuring" | "complete"

// ============================================================================
// NODE TYPES (matching Build page)
// ============================================================================

const nodeTypes = {
  domainController: ({ data }: { data: any }) => (
    <div className={`p-4 rounded-xl shadow-2xl relative border backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    } ${
      data.isSub
        ? "bg-gradient-to-br from-purple-600 to-violet-700 shadow-purple-900/50 border-purple-500/30"
        : "bg-gradient-to-br from-pink-600 to-rose-700 shadow-pink-900/50 border-pink-500/30"
    } ${data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-base-100" : ""} text-white`}>
      {data.locked && (
        <div className="absolute -top-2 -right-2 bg-yellow-500 text-black rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold">
          L
        </div>
      )}
      {data.hasPublicIP && (
        <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
          Public IP
        </div>
      )}
      <strong className="text-sm font-bold">{data.isSub ? "Sub DC" : "Domain Controller"}</strong>
      <div className="text-xs mt-2 space-y-1">
        <div className="font-semibold">{data.domainControllerName}</div>
        <div className={data.isSub ? "text-purple-100" : "text-pink-100"}>{data.domainName}</div>
        <div className={data.isSub ? "text-purple-200" : "text-pink-200"}>IP: {data.privateIPAddress}</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#fff", width: 12, height: 12, border: data.isSub ? "2px solid #9333ea" : "2px solid #ec4899" }} />
      <Handle type="target" position={Position.Left} style={{ background: "#fff", width: 12, height: 12, border: data.isSub ? "2px solid #9333ea" : "2px solid #ec4899" }} />
    </div>
  ),
  workstation: ({ data }: { data: any }) => (
    <div className={`bg-gradient-to-br from-emerald-600 to-teal-700 text-white p-4 rounded-xl shadow-2xl shadow-emerald-900/50 relative border border-emerald-500/30 backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    } ${data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-base-100" : ""}`}>
      {data.locked && (
        <div className="absolute -top-2 -right-2 bg-yellow-500 text-black rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold">
          L
        </div>
      )}
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
      <Handle type="target" position={Position.Left} style={{ background: "#fff", width: 12, height: 12, border: "2px solid #10b981" }} />
      <Handle type="source" position={Position.Right} style={{ background: "#fff", width: 12, height: 12, border: "2px solid #10b981" }} />
    </div>
  ),
  jumpbox: ({ data }: { data: any }) => (
    <div className="bg-gradient-to-br from-orange-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-orange-900/50 relative border border-orange-400/30 backdrop-blur-sm">
      <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
        Public IP
      </div>
      <strong className="text-sm font-bold">Jumpbox</strong>
      <div className="text-xs mt-2">
        <div className="text-orange-100">IP: {data.privateIPAddress}</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#fff", width: 12, height: 12, border: "2px solid #f97316" }} />
      <Handle type="target" position={Position.Left} style={{ background: "#fff", width: 12, height: 12, border: "2px solid #f97316" }} />
    </div>
  ),
  certificateAuthority: ({ data }: { data: any }) => (
    <div className={`bg-gradient-to-br from-yellow-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-yellow-900/50 relative border border-yellow-400/30 backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    } ${data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-base-100" : ""}`}>
      {data.locked && (
        <div className="absolute -top-2 -right-2 bg-yellow-500 text-black rounded-full w-6 h-6 flex items-center justify-center text-xs">
          🔒
        </div>
      )}
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
      <Handle type="target" position={Position.Left} style={{ background: "#fff", width: 12, height: 12, border: "2px solid #eab308" }} />
    </div>
  ),
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function BloodHoundImport() {
  // Step state
  const [step, setStep] = useState<Step>("upload")
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  
  // Upload state
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  
  // Options
  const [includeAllMachines, setIncludeAllMachines] = useState(true)
  const [adminUsername, setAdminUsername] = useState("labadmin")
  const [adminPassword, setAdminPassword] = useState("P@ssw0rd123!")
  
  // Topology state
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const nodeIdCounter = React.useRef(1) // Counter for unique node IDs
  const edgeIdCounter = React.useRef(1) // Counter for unique edge IDs
  const [lockedNodeIds, setLockedNodeIds] = useState<Set<string>>(new Set())
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateResult, setGenerateResult] = useState<GenerateResult | null>(null)
  const [selectedNode, setSelectedNode] = useState<any>(null) // For editing locked nodes
  
  // Deployment state
  const [deploymentId, setDeploymentId] = useState<string | null>(null)
  const [deploymentItems, setDeploymentItems] = useState<DeploymentItem[]>([])
  const [isDeploying, setIsDeploying] = useState(false)
  
  // Configuration state (post-deployment)
  const [configSteps, setConfigSteps] = useState<ConfigurationStep[]>([])
  const [isConfiguring, setIsConfiguring] = useState(false)
  
  // Error state
  const [error, setError] = useState<string | null>(null)

  // ============================================================================
  // CHECK FOR ACTIVE SESSION ON PAGE LOAD
  // ============================================================================
  
  useEffect(() => {
    const checkActiveSession = async () => {
      try {
        const response = await fetch(GlobalConfigs.bloodhoundActiveSessionEndpoint)
        
        if (!response.ok) {
          setIsLoadingSession(false)
          return
        }
        
        const data = await response.json()
        
        if (!data.active_session) {
          setIsLoadingSession(false)
          return
        }
        
        const session = data.active_session
        
        // Restore the upload result
        setUploadResult({
          success: true,
          upload_id: session.upload_id,
          domain: session.domain,
          summary: session.summary,
          attack_paths: session.attack_paths,
        })
        
        // Restore deployment ID if present
        if (session.deploymentID) {
          setDeploymentId(session.deploymentID)
        }
        
        // Restore topology if present
        if (session.topology) {
          const flowNodes = session.topology.nodes.map((node: any, index: number) => ({
            id: node.id,
            type: node.type,
            position: node.position || { x: 100 + (index % 3) * 300, y: 100 + Math.floor(index / 3) * 200 },
            data: { ...node.data, locked: true },
          }))
          
          const flowEdges = session.topology.edges.map((edge: any) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: "smoothstep",
            markerEnd: { type: MarkerType.ArrowClosed },
          }))
          
          setNodes(flowNodes)
          setEdges(flowEdges)
          setLockedNodeIds(new Set(flowNodes.map((n: any) => n.id)))
          
          // Track used IPs
          const ips = new Set<string>()
          flowNodes.forEach((n: any) => {
            if (n.data?.privateIPAddress) {
              ips.add(n.data.privateIPAddress)
            }
          })
          setUsedIPs(ips)
          
          // Restore generate result
          setGenerateResult({
            success: true,
            scenario_name: `bloodhound-${session.upload_id}`,
            topology: session.topology,
            users_to_create: session.users || [],
            attacks_to_enable: session.attacks || [],
          })
        }
        
        // Determine which step to restore to
        switch (session.step) {
          case "upload":
            // Session exists but no topology - go to preview
            setStep("preview")
            break
          case "topology":
            setStep("topology")
            break
          case "deploying":
            setIsDeploying(true)
            setStep("deploying")
            break
          case "configuring-users":
          case "configuring-attacks":
            setStep("configuring")
            break
          case "deploy-failed":
            setStep("topology") // Let them try again
            setError("Previous deployment failed. You can try deploying again.")
            break
          default:
            setStep("preview")
        }
        
      } catch (err) {
        console.error("BloodHound: Error checking active session:", err)
      } finally {
        setIsLoadingSession(false)
      }
    }
    
    checkActiveSession()
  }, [setNodes, setEdges])

  // Form state for adding nodes (matching Build page)
  const [formData, setFormData] = useState({
    type: "domainController",
    domainControllerName: "",
    domainName: "",
    workstationName: "",
    caName: "",
    privateIPAddress: "",
    hasPublicIP: false,
  })
  const [selectedRange, setSelectedRange] = useState("")
  const [availableIPs, setAvailableIPs] = useState<string[]>([])
  const [usedIPs, setUsedIPs] = useState<Set<string>>(new Set())

  // IP address utilities
  const generateIPRange = (start: string, end: string): string[] => {
    const ips: string[] = []
    const base = start.split(".").slice(0, 3).join(".")
    const s = parseInt(start.split(".")[3], 10)
    const e = parseInt(end.split(".")[3], 10)
    for (let i = s; i <= e; i++) {
      ips.push(`${base}.${i}`)
    }
    return ips
  }

  const ipRanges: Record<string, string[]> = {
    "10.10.0.0/24": generateIPRange("10.10.0.5", "10.10.0.250"),
    "172.16.0.0/24": generateIPRange("172.16.0.5", "172.16.0.250"),
    "192.168.0.0/24": generateIPRange("192.168.0.5", "192.168.0.250"),
  }

  const handleRangeSelection = (range: string) => {
    setSelectedRange(range)
    if (range) {
      const allIPs = ipRanges[range] || []
      const available = allIPs.filter((ip) => !usedIPs.has(ip))
      setAvailableIPs(available)
      if (available.length > 0) {
        setFormData((prev) => ({ ...prev, privateIPAddress: available[0] }))
      }
    } else {
      setAvailableIPs([])
    }
  }

  const addNode = () => {
    if (!formData.privateIPAddress) {
      alert("Please select an IP address")
      return
    }

    const newId = `node-${nodeIdCounter.current++}`
    let newNode: any

    if (formData.type === "domainController") {
      if (!formData.domainControllerName || !formData.domainName) {
        alert("Please enter DC Name and Domain Name")
        return
      }
      newNode = {
        id: newId,
        type: "domainController",
        position: { x: 400, y: 100 + nodes.length * 100 },
        data: {
          domainControllerName: formData.domainControllerName,
          domainName: formData.domainName,
          privateIPAddress: formData.privateIPAddress,
          hasPublicIP: formData.hasPublicIP,
        },
      }
    } else if (formData.type === "workstation") {
      if (!formData.workstationName) {
        alert("Please enter Workstation Name")
        return
      }
      newNode = {
        id: newId,
        type: "workstation",
        position: { x: 600, y: 100 + nodes.length * 100 },
        data: {
          workstationName: formData.workstationName,
          privateIPAddress: formData.privateIPAddress,
          hasPublicIP: formData.hasPublicIP,
        },
      }
    } else if (formData.type === "certificateAuthority") {
      if (!formData.caName) {
        alert("Please enter CA Name")
        return
      }
      newNode = {
        id: newId,
        type: "certificateAuthority",
        position: { x: 200, y: 100 + nodes.length * 100 },
        data: {
          caName: formData.caName,
          privateIPAddress: formData.privateIPAddress,
          hasPublicIP: formData.hasPublicIP,
        },
      }
    } else if (formData.type === "jumpbox") {
      newNode = {
        id: newId,
        type: "jumpbox",
        position: { x: 50, y: 50 },
        data: {
          privateIPAddress: formData.privateIPAddress,
        },
      }
    } else {
      return
    }

    setNodes((nds) => [...nds, newNode])
    setUsedIPs((prev) => new Set([...Array.from(prev), formData.privateIPAddress]))
    
    // Reset form
    setFormData({
      type: "domainController",
      domainControllerName: "",
      domainName: "",
      workstationName: "",
      caName: "",
      privateIPAddress: "",
      hasPublicIP: false,
    })
    setSelectedRange("")
    setAvailableIPs([])
  }

  // ============================================================================
  // FILE HANDLING
  // ============================================================================
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile?.name.endsWith(".zip")) {
      setFile(droppedFile)
    } else {
      setError("Please upload a .zip file")
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      setFile(selectedFile)
    }
  }

  // ============================================================================
  // API CALLS
  // ============================================================================

  const handleUpload = async () => {
    if (!file) return
    setIsUploading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch(GlobalConfigs.bloodhoundUploadEndpoint, {
        method: "POST",
        body: formData,
      })

      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Upload failed")

      setUploadResult(data)
      setStep("preview")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setIsUploading(false)
    }
  }

  // Hierarchical LEFT-TO-RIGHT layout function (matches Build page layout)
  // ============================================================================
  // VALIDATION FUNCTIONS
  // ============================================================================
  
  const validateCAPlacement = (flowNodes: any[], flowEdges: any[]) => {
    const errors: string[] = []
    
    // Find all CA nodes
    const caNodes = flowNodes.filter((n: any) => n.type === "certificateAuthority")
    
    if (caNodes.length === 0) {
      // No CAs to validate
      return { errors: [] }
    }
    
    // Build node map for quick lookup
    const nodeMap = new Map(flowNodes.map((n: any) => [n.id, n]))
    
    // Validate each CA
    caNodes.forEach((ca: any) => {
      const caName = ca.data?.label || ca.id
      
      // Find all edges where CA is source or target
      const caEdges = flowEdges.filter((edge: any) => 
        edge.source === ca.id || edge.target === ca.id
      )
      
      if (caEdges.length === 0) {
        errors.push(`CA "${caName}" is not connected to any domain controller`)
        return
      }
      
      // Check each connection
      caEdges.forEach((edge: any) => {
        const connectedNodeId = edge.source === ca.id ? edge.target : edge.source
        const connectedNode = nodeMap.get(connectedNodeId)
        
        if (!connectedNode) {
          errors.push(`CA "${caName}" has an invalid connection (node not found)`)
          return
        }
        
        // CA can only connect to domain controllers
        if (connectedNode.type !== "domainController") {
          errors.push(
            `CA "${caName}" cannot connect to ${connectedNode.type} "${connectedNode.data?.label || connectedNodeId}". ` +
            `CAs can only connect to domain controllers.`
          )
          return
        }
        
        // CA can only connect to root DCs (not sub DCs)
        if (connectedNode.data?.isSub === true) {
          errors.push(
            `CA "${caName}" cannot connect to sub-domain controller "${connectedNode.data?.label || connectedNodeId}". ` +
            `CAs must only connect to the root domain controller.`
          )
        }
      })
    })
    
    return { errors }
  }

  // ============================================================================
  // LAYOUT FUNCTIONS
  // ============================================================================
  
  const applyHierarchicalLayout = (flowNodes: any[], flowEdges: any[]) => {
    const spacing = { x: 280, y: 150 }
    
    // Build adjacency from edges
    const childrenMap = new Map<string, string[]>()
    const hasParent = new Set<string>()
    
    flowEdges.forEach((edge: any) => {
      if (!childrenMap.has(edge.source)) {
        childrenMap.set(edge.source, [])
      }
      childrenMap.get(edge.source)!.push(edge.target)
      hasParent.add(edge.target)
    })
    
    // Find root nodes (no incoming edges) - these are root DCs
    const rootNodes = flowNodes.filter((n: any) => 
      n.type === "domainController" && !hasParent.has(n.id)
    )
    
    // Find jumpboxes
    const jumpboxes = flowNodes.filter((n: any) => n.type === "jumpbox")
    
    // Position root nodes on the left, stacked vertically
    rootNodes.forEach((root: any, index: number) => {
      root.position = { x: 100, y: 100 + index * spacing.y * 2 }
      positionChildrenRecursive(root, 1, flowNodes, childrenMap, spacing)
    })
    
    // Position jumpboxes at the far right
    const maxX = Math.max(...flowNodes.map((n: any) => n.position?.x || 0), 100)
    jumpboxes.forEach((jumpbox: any, index: number) => {
      jumpbox.position = { x: maxX + spacing.x, y: 100 + index * spacing.y }
    })
    
    function positionChildrenRecursive(
      parent: any,
      depth: number,
      allNodes: any[],
      childrenMap: Map<string, string[]>,
      spacing: { x: number; y: number }
    ) {
      const childIds = childrenMap.get(parent.id) || []
      const children = childIds
        .map((id: string) => allNodes.find((n: any) => n.id === id))
        .filter(Boolean)
      
      if (children.length === 0) return
      
      // Position children to the right of parent, centered vertically
      children.forEach((child: any, index: number) => {
        child.position = {
          x: parent.position.x + spacing.x,
          y: parent.position.y - ((children.length - 1) * spacing.y) / 2 + index * spacing.y,
        }
        // Recursively position grandchildren
        positionChildrenRecursive(child, depth + 1, allNodes, childrenMap, spacing)
      })
    }
  }

  const handleGenerateTopology = async () => {
    if (!uploadResult) return
    setIsGenerating(true)
    setError(null)

    try {
      const response = await fetch(GlobalConfigs.bloodhoundGenerateTopologyEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: uploadResult.upload_id,
          options: {
            admin_username: adminUsername,
            admin_password: adminPassword,
            include_all_machines: includeAllMachines,
          },
        }),
      })

      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to generate topology")

      setGenerateResult(data)

      // Convert topology to ReactFlow nodes/edges
      const flowNodes = data.topology.nodes.map((node: any, index: number) => ({
        id: node.id,
        type: node.type,
        position: node.position || { x: 0, y: 0 },
        data: { ...node.data, locked: true },
      }))

      // Create node map for edge processing
      const nodeMap = new Map(flowNodes.map((n: any) => [n.id, n] as const))

      // Ensure all edges have unique IDs and correct handles
      const flowEdges = data.topology.edges.map((edge: any, index: number) => {
        const edgeId = edge.id && typeof edge.id === 'string' ? edge.id : `edge-${index + 1}`
        const targetNode = nodeMap.get(edge.target) as { id: string; type: string; position: any; data: any } | undefined
        const isJumpboxConnection = targetNode?.type === "jumpbox"
        
        return {
          id: edgeId,
          source: edge.source,
          target: edge.target,
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed },
          sourceHandle: isJumpboxConnection ? "right" : (edge.sourceHandle || undefined),
          targetHandle: edge.targetHandle || undefined
        }
      })

      // Update nodeIdCounter based on loaded nodes
      let maxNodeId = 0
      flowNodes.forEach((node: any) => {
        if (node.id && typeof node.id === 'string') {
          const match = node.id.match(/^node-(\d+)$/)
          if (match) {
            const nodeNum = parseInt(match[1], 10)
            if (nodeNum > maxNodeId) maxNodeId = nodeNum
          }
        }
      })
      nodeIdCounter.current = maxNodeId + 1

      // Update edgeIdCounter based on loaded edges
      let maxEdgeId = 0
      flowEdges.forEach((edge: any) => {
        if (edge.id && typeof edge.id === 'string') {
          const match = edge.id.match(/^edge-(\d+)$/)
          if (match) {
            const edgeNum = parseInt(match[1], 10)
            if (edgeNum > maxEdgeId) maxEdgeId = edgeNum
          }
        }
      })
      edgeIdCounter.current = maxEdgeId + 1


      // Validate CA placement rules
      const validationResult = validateCAPlacement(flowNodes, flowEdges)
      if (validationResult.errors.length > 0) {
        setError(`Cannot import topology:\n${validationResult.errors.join('\n')}`)
        return
      }

      // Apply hierarchical LEFT-TO-RIGHT layout
      applyHierarchicalLayout(flowNodes, flowEdges)

      setNodes(flowNodes)
      setEdges(flowEdges)
      setLockedNodeIds(new Set(flowNodes.map((n: any) => n.id)))
      setStep("topology")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate topology")
    } finally {
      setIsGenerating(false)
    }
  }

  // Custom edge change handler
  const handleEdgesChange = useCallback((changes: any[]) => {
    onEdgesChange(changes)
  }, [onEdgesChange])

  // Prevent deletion of locked nodes
  const handleNodesChange = useCallback(
    (changes: any[]) => {
      const filteredChanges = changes.filter((change) => {
        if (change.type === "remove" && lockedNodeIds.has(change.id)) {
          return false // Prevent deletion
        }
        return true
      })
      onNodesChange(filteredChanges)
    },
    [onNodesChange, lockedNodeIds]
  )

  const onConnect = useCallback(
    (params: any) => {
      if (!params.source || !params.target) return
      
      const sourceNode = nodes.find((n) => n.id === params.source)
      const targetNode = nodes.find((n) => n.id === params.target)
      
      if (!sourceNode || !targetNode) return
      
      const already = edges.some((e) => e.source === params.source && e.target === params.target)
      if (already) {
        alert("Connection already exists")
        return
      }
      
      const newEdgeConfig = {
        ...params,
        id: `edge-${edgeIdCounter.current++}`,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed },
      }
      
      // If connecting DC to DC, mark target as Sub DC
      if (sourceNode.type === "domainController" && targetNode.type === "domainController") {
        setNodes((nds) =>
          nds.map((node) =>
            node.id === targetNode.id
              ? { ...node, data: { ...node.data, isSub: true } }
              : node
          )
        )
      }
      
      // If connecting workstation to DC, update workstation domain
      if (sourceNode.type === "domainController" && targetNode.type === "workstation") {
        setNodes((nds) =>
          nds.map((node) =>
            node.id === targetNode.id
              ? { ...node, data: { ...node.data, domainName: sourceNode.data.domainName } }
              : node
          )
        )
      }
      
      setEdges((eds) => addEdge(newEdgeConfig, eds))
    },
    [edges, nodes, setEdges, setNodes]
  )

  // Handle node click - allow editing locked nodes (e.g., toggle public IP)
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: any) => {
      // Only show edit panel for locked nodes (BloodHound-generated nodes)
      if (lockedNodeIds.has(node.id)) {
        setSelectedNode(node)
      }
    },
    [lockedNodeIds]
  )

  // Toggle public IP for selected node
  const togglePublicIP = useCallback(() => {
    if (!selectedNode) return
    
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, hasPublicIP: !n.data.hasPublicIP } }
          : n
      )
    )
    // Update the selected node state too
    setSelectedNode((prev: any) => 
      prev ? { ...prev, data: { ...prev.data, hasPublicIP: !prev.data.hasPublicIP } } : null
    )
  }, [selectedNode, setNodes])

  // ============================================================================
  // DEPLOYMENT
  // ============================================================================

  const handleDeploy = async () => {
    if (!generateResult) return
    setIsDeploying(true)
    setError(null)
    setDeploymentItems([])

    try {
      // Build topology from current nodes/edges
      const topology = {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
        })),
      }

      const response = await fetch(GlobalConfigs.bloodhoundDeployEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: uploadResult?.upload_id,
          topology,
          scenario_name: generateResult.scenario_name,
        }),
      })

      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Deployment failed")

      setDeploymentId(data.deploymentID)
      setStep("deploying")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deployment failed")
      setIsDeploying(false)
    }
  }

  // ============================================================================
  // POST-DEPLOYMENT CONFIGURATION
  // ============================================================================

  const startPostDeploymentConfig = useCallback(async (depId: string, upId: string) => {
    setIsConfiguring(true)
    setStep("configuring")

    const steps: ConfigurationStep[] = [
      { name: "Creating Users", status: "pending" },
      { name: "Enabling Attacks", status: "pending" },
    ]
    setConfigSteps(steps)

    // Step 1: Create users
    setConfigSteps((prev) => prev.map((s, i) => (i === 0 ? { ...s, status: "running" } : s)))

    try {
      const userResponse = await fetch(GlobalConfigs.bloodhoundConfigureUsersEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deploymentID: depId,
          upload_id: upId,
        }),
      })

      const userData = await userResponse.json()
      
      if (!userResponse.ok) {
        throw new Error(userData.error || "Failed to create users")
      }

      setConfigSteps((prev) =>
        prev.map((s, i) => (i === 0 ? { ...s, status: "succeeded", message: `Created ${userData.users_created?.length || 0} users` } : s))
      )
    } catch (err) {
      console.error("BloodHound: Error creating users:", err)
      setConfigSteps((prev) =>
        prev.map((s, i) =>
          i === 0 ? { ...s, status: "failed", message: err instanceof Error ? err.message : "Failed" } : s
        )
      )
    }

    // Step 2: Enable attacks
    setConfigSteps((prev) => prev.map((s, i) => (i === 1 ? { ...s, status: "running" } : s)))

    try {
      const attackResponse = await fetch(GlobalConfigs.bloodhoundConfigureAttacksEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deploymentID: depId,
          upload_id: upId,
        }),
      })

      const attackData = await attackResponse.json()

      if (!attackResponse.ok) {
        throw new Error(attackData.error || "Failed to enable attacks")
      }

      // Build message including unsupported attacks info
      let attackMessage = "Attacks enabled successfully"
      const enabledCount = Object.values(attackData.attacks_enabled || {}).reduce((acc: number, arr: any) => acc + (arr as any[]).length, 0)
      if (enabledCount > 0) {
        attackMessage = `Enabled ${enabledCount} attack(s)`
      }
      
      // Add unsupported attacks notice if any
      const unsupportedCount = attackData.unsupported_attacks_count || 0
      if (unsupportedCount > 0) {
        attackMessage += `. ${unsupportedCount} unsupported attack(s) found in BloodHound data.`
      }

      setConfigSteps((prev) =>
        prev.map((s, i) => (i === 1 ? { ...s, status: "succeeded", message: attackMessage } : s))
      )
      
      // Poll attack status until all attacks complete - WAIT before transitioning
      setConfigSteps((prev) =>
        prev.map((s, i) => (i === 1 ? { ...s, message: attackMessage + " (waiting for completion...)" } : s))
      )
      
      const pollAttackStatus = async (): Promise<boolean> => {
        try {
          const statusResponse = await fetch(GlobalConfigs.checkAttackStatusEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ deploymentId: depId }),
          })
          const statusData = await statusResponse.json()

          // If there are still attacks in progress, continue polling
          if (statusData.attacksInProgress && Object.keys(statusData.attacksInProgress).length > 0) {
            return true // Still in progress
          }
          return false // All done
        } catch (error) {
          console.error("BloodHound: Error checking attack status:", error)
          return false // Stop polling on error
        }
      }

      // Poll until complete - use Promise to wait
      await new Promise<void>((resolve) => {
        const pollInterval = setInterval(async () => {
          const stillInProgress = await pollAttackStatus()
          if (!stillInProgress) {
            clearInterval(pollInterval)
            setConfigSteps((prev) =>
              prev.map((s, i) => (i === 1 ? { ...s, message: attackMessage + " ✓" } : s))
            )
            resolve()
          }
        }, 5000)

        // Stop polling after 10 minutes (failsafe) and resolve anyway
        setTimeout(() => {
          clearInterval(pollInterval)
          resolve()
        }, 600000)
      })
      
    } catch (err) {
      console.error("BloodHound: Error enabling attacks:", err)
      setConfigSteps((prev) =>
        prev.map((s, i) =>
          i === 1 ? { ...s, status: "failed", message: err instanceof Error ? err.message : "Failed" } : s
        )
      )
    }

    // NOW transition after attacks complete
    setIsConfiguring(false)
    setStep("complete")

    // Clear the active session since we're done
    try {
      await fetch(GlobalConfigs.bloodhoundClearSessionEndpoint, { method: "POST" })
    } catch (e) {
    }

    // Set the deployment as current environment and redirect to home page
    SetCookie("deploymentID", depId)
    
    setTimeout(() => {
      window.location.href = "/"
    }, 2000)
  }, [])

  // Poll deployment status
  useEffect(() => {
    if (step !== "deploying" || !deploymentId) {
      return
    }

    
    // Capture these values for use in the polling function
    const currentUploadId = uploadResult?.upload_id
    const currentDeploymentId = deploymentId

    const pollStatus = async () => {
      try {
        const response = await fetch(GlobalConfigs.getDeploymentStateEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ deploymentID: currentDeploymentId }),
        })

        if (!response.ok) {
          return
        }

        const data = await response.json()
        const details = data.details || {}

        // Build unified list
        const allItems: DeploymentItem[] = []
        const seenNames = new Set<string>()

        ;(details.failed || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "failed" })
          }
        })
        ;(details.running || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "running" })
          }
        })
        ;(details.succeeded || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "succeeded" })
          }
        })

        allItems.sort((a, b) => {
          const order = { running: 0, succeeded: 1, failed: 2, pending: 3 }
          return order[a.status] - order[b.status]
        })

        setDeploymentItems(allItems)

        // Check if complete
        if (data.message === "deployed") {
          setIsDeploying(false)
          // Call with explicit values to avoid closure issues
          if (currentUploadId) {
            startPostDeploymentConfig(currentDeploymentId, currentUploadId)
          } else {
            console.error("BloodHound: No upload_id available for post-deployment config!")
            setStep("complete")
          }
        } else if (data.message === "failed") {
          setIsDeploying(false)
          setError("Deployment failed. Check the failed resources above.")
        }
      } catch (err) {
        console.error("Error polling deployment status:", err)
      }
    }

    pollStatus()
    const interval = setInterval(pollStatus, 5000)
    return () => clearInterval(interval)
  }, [step, deploymentId, uploadResult?.upload_id, startPostDeploymentConfig])

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const getStepNumber = (s: Step): number => {
    const steps: Step[] = ["upload", "preview", "topology", "deploying", "configuring", "complete"]
    return steps.indexOf(s) + 1
  }

  const isStepComplete = (s: Step): boolean => {
    const current = getStepNumber(step)
    const target = getStepNumber(s)
    return target < current
  }

  const isStepActive = (s: Step): boolean => step === s

  // ============================================================================
  // CLEAR SESSION (Start New Import)
  // ============================================================================
  
  const handleClearSession = async () => {
    if (!uploadResult?.upload_id) return
    
    const confirmed = window.confirm(
      "This will clear your current BloodHound import session. Are you sure?"
    )
    if (!confirmed) return
    
    try {
      await fetch(`${GlobalConfigs.bloodhoundClearSessionEndpoint}/${uploadResult.upload_id}`, {
        method: "DELETE",
      })
    } catch (err) {
      console.error("Error clearing session:", err)
    }
    
    // Reset all state
    setStep("upload")
    setFile(null)
    setUploadResult(null)
    setGenerateResult(null)
    setNodes([])
    setEdges([])
    setLockedNodeIds(new Set())
    setDeploymentId(null)
    setDeploymentItems([])
    setConfigSteps([])
    setError(null)
    setIsDeploying(false)
    setIsConfiguring(false)
    setUsedIPs(new Set())
  }

  // ============================================================================
  // RENDER
  // ============================================================================

  // Show loading state while checking for active session
  if (isLoadingSession) {
    return (
      <div className="page-container">
        <h1 className="base-title-centered base-text-color mb-4">
          BloodHound Import
        </h1>
        <div className="flex items-center justify-center py-12">
          <div className="text-base-content/60">Checking for active session...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <h1 className="base-title-centered base-text-color mb-4">
        BloodHound Import
      </h1>
      <p className="text-center text-base-content/60 mb-6">
        Upload BloodHound collection data to automatically generate a replica Active Directory environment
      </p>

        {/* Session Info Banner - show when resuming an existing session */}
        {uploadResult && step !== "upload" && step !== "complete" && (
          <div className="mb-6 p-4 bg-primary/30 border border-primary/50 rounded-xl flex items-center justify-between">
            <div className="flex items-center gap-3 text-primary">
              <span className="text-xl">🔄</span>
              <span>
                Continuing import session: <span className="font-mono font-bold">{uploadResult.upload_id}</span>
                {uploadResult.domain?.name && ` (${uploadResult.domain.name})`}
              </span>
            </div>
            <button
              onClick={handleClearSession}
              className="px-4 py-2 bg-base-300 hover:bg-base-300 text-base-content/80 rounded-lg text-sm transition-colors"
            >
              Start New Import
            </button>
          </div>
        )}

        {/* Progress Steps */}
        <div className="flex items-center justify-between mb-8 max-w-3xl mx-auto">
          {(["upload", "preview", "topology", "deploying", "configuring", "complete"] as const).map((s, idx) => (
            <React.Fragment key={s}>
              <div className="flex flex-col items-center">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                    isStepComplete(s)
                      ? "bg-primary text-white"
                      : isStepActive(s)
                      ? "bg-primary text-white"
                      : "bg-base-300 text-base-content/60"
                  }`}
                >
                  {isStepComplete(s) ? "✓" : idx + 1}
                </div>
                <span className="text-xs text-base-content/60 mt-2 capitalize">{s === "configuring" ? "config" : s}</span>
              </div>
              {idx < 5 && (
                <div className={`flex-1 h-1 mx-2 ${isStepComplete(s) ? "bg-primary" : "bg-base-300"}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Error Display */}
        {error && (
          <div className="p-4 bg-error/30 border border-error/50 rounded-xl text-error flex items-center gap-3">
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-error hover:text-error">✕</button>
          </div>
        )}

        {/* STEP 1: Upload */}
        {step === "upload" && (
          <div className="form-section">
            <h2 className="form-section-title">Upload BloodHound Data</h2>
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer ${
                isDragging ? "border-primary bg-primary/10" : file ? "border-emerald-500 bg-emerald-500/10" : "border-base-300 hover:border-base-300 bg-base-200/30"
              }`}
            >
              {file ? (
                <div className="space-y-3">
                  <div className="w-16 h-16 mx-auto bg-emerald-500/20 rounded-full flex items-center justify-center">✓</div>
                  <p className="text-base-content/70 font-medium">{file.name}</p>
                  <p className="text-base-content/60 text-sm">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="w-16 h-16 mx-auto bg-base-300/50 rounded-full flex items-center justify-center">📁</div>
                  <p className="text-base-content/80">Drag and drop your BloodHound ZIP file here</p>
                  <p className="text-base-content0 text-sm">or click to browse</p>
                </div>
              )}
              <input type="file" accept=".zip" onChange={handleFileSelect} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={handleUpload}
                disabled={!file || isUploading}
                className={`btn-primary px-6 py-3 ${(!file || isUploading) ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {isUploading ? "Uploading..." : "Upload & Parse"}
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: Preview */}
        {step === "preview" && uploadResult && (
          <div className="space-y-6">
            {/* Domain Info */}
            <div className="form-section">
              <h2 className="form-section-title">Domain Information</h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-base-200/50 rounded-lg p-4 border border-base-300/50">
                  <div className="text-base-content/60 text-xs uppercase mb-1">Domain</div>
                  <div className="text-base-content/70 font-semibold">{uploadResult.domain?.name || "Unknown"}</div>
                </div>
                <div className="bg-base-200/50 rounded-lg p-4 border border-base-300/50">
                  <div className="text-base-content/60 text-xs uppercase mb-1">Functional Level</div>
                  <div className="text-base-content/70 font-semibold">{uploadResult.domain?.functional_level || "Unknown"}</div>
                </div>
                <div className="bg-base-200/50 rounded-lg p-4 border border-base-300/50">
                  <div className="text-base-content/60 text-xs uppercase mb-1">Domain Controllers</div>
                  <div className="text-base-content/70 font-semibold">{uploadResult.summary.domain_controllers}</div>
                </div>
                <div className="bg-base-200/50 rounded-lg p-4 border border-base-300/50">
                  <div className="text-base-content/60 text-xs uppercase mb-1">Workstations</div>
                  <div className="text-base-content/70 font-semibold">{uploadResult.summary.workstations}</div>
                </div>
                <div className="bg-base-200/50 rounded-lg p-4 border border-base-300/50">
                  <div className="text-base-content/60 text-xs uppercase mb-1">Total Users</div>
                  <div className="text-base-content/70 font-semibold">{uploadResult.summary.total_users}</div>
                </div>
              </div>
            </div>

            {/* Attack Paths */}
            <div className="form-section">
              <h2 className="form-section-title">Detected Attack Paths</h2>
              <div className="space-y-3">
                {uploadResult.attack_paths.asrep_roastable.length > 0 && (
                  <div className="bg-error/20 border border-error/50 rounded-lg p-4">
                    <div className="text-error font-semibold mb-2">AS-REP Roastable ({uploadResult.attack_paths.asrep_roastable.length})</div>
                    <div className="flex flex-wrap gap-2">
                      {uploadResult.attack_paths.asrep_roastable.map((u) => (
                        <span key={u} className="bg-error/50 text-error-content px-2 py-1 rounded text-sm">{u}</span>
                      ))}
                    </div>
                  </div>
                )}
                {uploadResult.attack_paths.kerberoastable.length > 0 && (
                  <div className="bg-orange-900/20 border border-orange-700/50 rounded-lg p-4">
                    <div className="text-orange-400 font-semibold mb-2">Kerberoastable ({uploadResult.attack_paths.kerberoastable.length})</div>
                    <div className="flex flex-wrap gap-2">
                      {uploadResult.attack_paths.kerberoastable.map((u) => (
                        <span key={u} className="bg-orange-800/50 text-orange-200 px-2 py-1 rounded text-sm">{u}</span>
                      ))}
                    </div>
                  </div>
                )}
                {uploadResult.attack_paths.unconstrained_delegation.length > 0 && (
                  <div className="bg-purple-900/20 border border-purple-700/50 rounded-lg p-4">
                    <div className="text-purple-400 font-semibold mb-2">Unconstrained Delegation ({uploadResult.attack_paths.unconstrained_delegation.length})</div>
                    <div className="flex flex-wrap gap-2">
                      {uploadResult.attack_paths.unconstrained_delegation.map((c) => (
                        <span key={c} className="bg-purple-800/50 text-purple-200 px-2 py-1 rounded text-sm">{c}</span>
                      ))}
                    </div>
                  </div>
                )}
                {uploadResult.attack_paths.acl_attack_paths_count > 0 && (
                  <div className="bg-primary/20 border border-primary/50 rounded-lg p-4">
                    <div className="text-primary font-semibold">ACL Attack Paths: {uploadResult.attack_paths.acl_attack_paths_count}</div>
                  </div>
                )}
              </div>
            </div>

            {/* Import Options */}
            <div className="form-section">
              <h2 className="form-section-title">Import Options</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">Enterprise Admin Username</label>
                  <input
                    type="text"
                    value={adminUsername}
                    onChange={(e) => setAdminUsername(e.target.value)}
                    className="form-input w-full"
                  />
                </div>
                <div>
                  <label className="form-label">Enterprise Admin Password</label>
                  <input
                    type="password"
                    value={adminPassword}
                    onChange={(e) => setAdminPassword(e.target.value)}
                    className="form-input w-full"
                  />
                </div>
              </div>
              <div className="mt-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeAllMachines}
                    onChange={(e) => setIncludeAllMachines(e.target.checked)}
                    className="w-5 h-5 rounded border-base-300 bg-base-200 text-primary"
                  />
                  <span className="text-base-content/80">Include All Machines</span>
                </label>
                <p className="text-base-content0 text-sm mt-1 ml-8">
                  {includeAllMachines
                    ? "All machines from BloodHound will be included"
                    : "Only machines needed for detected attack paths will be included"}
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-between">
              <button onClick={() => setStep("upload")} className="btn-secondary px-6 py-3">
                ← Back
              </button>
              <button
                onClick={handleGenerateTopology}
                disabled={isGenerating}
                className={`btn-primary px-6 py-3 ${isGenerating ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {isGenerating ? "Generating..." : "Generate Topology →"}
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: Topology Builder - Matching Build page exactly */}
        {step === "topology" && (
          <div className="space-y-6">
            {/* Configuration Section */}
            <div className="form-section">
              <h4 className="form-section-title text-base mb-3">
                Add Infrastructure Components
              </h4>
              <p className="text-base-content/60 text-sm mb-4">
                🔒 Locked nodes are from BloodHound and cannot be deleted. Add more nodes below if needed.
              </p>

              <div className="responsive-grid">
                <div>
                  <label className="form-label">Node Type</label>
                  <select
                    value={formData.type}
                    onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                    className="form-select"
                  >
                    <option value="domainController">Domain Controller</option>
                    <option value="workstation">Workstation</option>
                    <option value="certificateAuthority">Certificate Authority</option>
                    <option value="jumpbox">Jumpbox</option>
                  </select>
                </div>

                {formData.type === "domainController" && (
                  <>
                    <div>
                      <label className="form-label">DC Name</label>
                      <input
                        type="text"
                        value={formData.domainControllerName}
                        onChange={(e) => setFormData({ ...formData, domainControllerName: e.target.value })}
                        className="form-input"
                      />
                    </div>
                    <div>
                      <label className="form-label">Domain Name</label>
                      <input
                        type="text"
                        value={formData.domainName}
                        onChange={(e) => setFormData({ ...formData, domainName: e.target.value })}
                        className="form-input"
                      />
                    </div>
                  </>
                )}

                {formData.type === "workstation" && (
                  <div>
                    <label className="form-label">Workstation Name</label>
                    <input
                      type="text"
                      value={formData.workstationName}
                      onChange={(e) => setFormData({ ...formData, workstationName: e.target.value })}
                      className="form-input"
                    />
                  </div>
                )}

                {formData.type === "certificateAuthority" && (
                  <div>
                    <label className="form-label">CA Name</label>
                    <input
                      type="text"
                      value={formData.caName}
                      onChange={(e) => setFormData({ ...formData, caName: e.target.value })}
                      className="form-input"
                    />
                  </div>
                )}

                <div>
                  <label className="form-label">IP Range</label>
                  <select
                    value={selectedRange}
                    onChange={(e) => handleRangeSelection(e.target.value)}
                    className="form-select"
                  >
                    <option value="">Select Range</option>
                    {Object.keys(ipRanges).map((range) => (
                      <option key={range} value={range}>{range}</option>
                    ))}
                  </select>
                </div>

                {selectedRange && (
                  <div>
                    <label className="form-label">IP Address</label>
                    <select
                      value={formData.privateIPAddress}
                      onChange={(e) => setFormData({ ...formData, privateIPAddress: e.target.value })}
                      className="form-select"
                    >
                      <option value="">Select IP</option>
                      {availableIPs.map((ip) => (
                        <option key={ip} value={ip}>{ip}</option>
                      ))}
                    </select>
                  </div>
                )}

                {formData.type !== "jumpbox" && (
                  <div className="flex items-center gap-3">
                    <label className="form-label mb-0">Public IP</label>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.hasPublicIP}
                        onChange={(e) => setFormData({ ...formData, hasPublicIP: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-base-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-base-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                      <span className="ml-2 text-sm text-base-content/80">{formData.hasPublicIP ? "Yes" : "No"}</span>
                    </label>
                  </div>
                )}

                <div className="flex items-end">
                  <button type="button" onClick={addNode} className="btn-primary w-full">
                    Add Node
                  </button>
                </div>
              </div>
            </div>

            {/* ReactFlow Canvas */}
            <div className="reactflow-container">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={handleNodesChange}
                onEdgesChange={handleEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                nodeTypes={nodeTypes}
                defaultEdgeOptions={{
                  type: "smoothstep",
                  markerEnd: { type: MarkerType.ArrowClosed },
                }}
                style={{ width: "100%", height: "100%" }}
                fitView
              >
                <Controls />
                <Background />
              </ReactFlow>
              
              {/* Node Edit Panel - appears when a locked node is clicked */}
              {selectedNode && (
                <div className="absolute top-4 right-4 bg-base-200 border border-base-300 rounded-lg p-4 shadow-xl z-50 min-w-[250px]">
                  <div className="flex justify-between items-center mb-3">
                    <h4 className="text-white font-semibold">
                      {selectedNode.data.domainControllerName || selectedNode.data.workstationName || selectedNode.data.jumpboxName || "Node"}
                    </h4>
                    <button 
                      onClick={() => setSelectedNode(null)}
                      className="text-base-content/60 hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                  
                  <div className="text-sm text-base-content/80 mb-3">
                    <div>Type: <span className="text-white">{selectedNode.type}</span></div>
                    {selectedNode.data.domainName && (
                      <div>Domain: <span className="text-white">{selectedNode.data.domainName}</span></div>
                    )}
                    <div>IP: <span className="text-white">{selectedNode.data.privateIPAddress}</span></div>
                  </div>
                  
                  <div className="border-t border-base-300 pt-3">
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedNode.data.hasPublicIP || false}
                        onChange={togglePublicIP}
                        className="form-checkbox h-4 w-4 text-cyan-500 rounded"
                      />
                      <span className="ml-2 text-sm text-base-content/80">
                        Public IP {selectedNode.data.hasPublicIP ? "(Enabled)" : "(Disabled)"}
                      </span>
                    </label>
                    {selectedNode.data.hasPublicIP && (
                      <p className="text-xs text-cyan-400 mt-1">
                        🌐 This node will have a public IP for external access
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex justify-between pt-4">
              <button onClick={() => setStep("preview")} className="btn-secondary px-6 py-3" disabled={isDeploying}>
                ← Back to Preview
              </button>
              <button 
                onClick={handleDeploy} 
                className={`btn-success btn-large ${isDeploying ? 'opacity-50 cursor-not-allowed' : ''}`}
                disabled={isDeploying}
              >
                {isDeploying ? (
                  <span className="flex items-center gap-2">
                    <svg 
                      className="animate-spin h-5 w-5" 
                      xmlns="http://www.w3.org/2000/svg" 
                      fill="none" 
                      viewBox="0 0 24 24"
                    >
                      <circle 
                        className="opacity-25" 
                        cx="12" 
                        cy="12" 
                        r="10" 
                        stroke="currentColor" 
                        strokeWidth="4"
                      />
                      <path 
                        className="opacity-75" 
                        fill="currentColor" 
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Deploying Environment...
                  </span>
                ) : (
                  "Deploy Environment"
                )}
              </button>
            </div>
          </div>
        )}

        {/* STEP 4: Deploying */}
        {step === "deploying" && (
          <div className="form-section">
            <h2 className="form-section-title flex items-center gap-3">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              Deploying Infrastructure...
            </h2>
            <p className="text-base-content/60 mb-6">Please wait while your environment is being deployed.</p>

            {deploymentItems.length > 0 ? (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {deploymentItems.map((item) => (
                  <div
                    key={item.name}
                    className={`flex items-center justify-between p-3 rounded-lg ${
                      item.status === "succeeded" ? "bg-success/30 border border-success/50" :
                      item.status === "running" ? "bg-primary/30 border border-primary/50" :
                      item.status === "failed" ? "bg-error/30 border border-error/50" :
                      "bg-base-300/30 border border-base-300/50"
                    }`}
                  >
                    <span className="font-mono text-sm text-base-content/70">{item.name}</span>
                    <span className={`text-xs font-semibold px-2 py-1 rounded ${
                      item.status === "succeeded" ? "bg-success text-success-content" :
                      item.status === "running" ? "bg-primary text-primary-content" :
                      item.status === "failed" ? "bg-error text-error-content" :
                      "bg-base-300 text-base-content/80"
                    }`}>
                      {item.status === "succeeded" ? "Completed" :
                       item.status === "running" ? "In Progress" :
                       item.status === "failed" ? "Failed" : "Pending"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-base-content0 italic">Initializing deployment...</div>
            )}
          </div>
        )}

        {/* STEP 5: Configuring */}
        {step === "configuring" && (
          <div className="form-section">
            <h2 className="form-section-title flex items-center gap-3">
              <div className="w-6 h-6 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
              Post-Deployment Configuration
            </h2>
            <p className="text-base-content/60 mb-6">Creating users and enabling attack configurations...</p>

            <div className="space-y-3">
              {configSteps.map((s, idx) => (
                <div
                  key={idx}
                  className={`flex items-center justify-between p-4 rounded-lg ${
                    s.status === "succeeded" ? "bg-success/30 border border-success/50" :
                    s.status === "running" ? "bg-purple-900/30 border border-purple-700/50" :
                    s.status === "failed" ? "bg-error/30 border border-error/50" :
                    "bg-base-300/30 border border-base-300/50"
                  }`}
                >
                  <div>
                    <span className="text-base-content/70 font-medium">{s.name}</span>
                    {s.message && <p className="text-sm text-base-content/60 mt-1">{s.message}</p>}
                  </div>
                  <span className={`text-xs font-semibold px-3 py-1 rounded ${
                    s.status === "succeeded" ? "bg-success text-success-content" :
                    s.status === "running" ? "bg-purple-700 text-purple-100" :
                    s.status === "failed" ? "bg-error text-error-content" :
                    "bg-base-300 text-base-content/80"
                  }`}>
                    {s.status === "succeeded" ? "✓ Done" :
                     s.status === "running" ? "Running..." :
                     s.status === "failed" ? "✕ Failed" : "Pending"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* STEP 6: Complete */}
        {step === "complete" && (
          <div className="form-section text-center py-12">
            <div className="w-20 h-20 mx-auto bg-primary/20 rounded-full flex items-center justify-center mb-6">
              <span className="text-4xl text-primary">✓</span>
            </div>
            <h2 className="text-2xl font-bold text-base-content mb-4">Environment Ready!</h2>
            <p className="text-base-content/60 mb-4">
              Your BloodHound replica environment has been deployed and configured successfully.
            </p>
            <p className="text-primary mb-8 animate-pulse">
              Redirecting to your environment...
            </p>
            <div className="flex justify-center gap-4">
              <button onClick={() => { SetCookie("deploymentID", deploymentId || ""); window.location.href = "/" }} className="btn-primary px-6 py-3">
                Go Now
              </button>
              <button onClick={() => { setStep("upload"); setFile(null); setUploadResult(null); }} className="btn-secondary px-6 py-3">
                Import Another
              </button>
            </div>
          </div>
        )}
    </div>
  )
}
