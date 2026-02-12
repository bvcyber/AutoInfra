"use client"

import React, { useState, useEffect, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  useEdgesState,
  useNodesState,
  Handle,
  Node,
  Edge,
  Connection,
  ConnectionLineType,
  MarkerType,
  Position,
} from "reactflow"
import "reactflow/dist/style.css"
import GlobalConfig from "@/app/app.config"
import { SetCookie, GetCookie, DeleteCookie } from "@/components/cookieHandler"
import EnvironmentInfo from "../EnvironmentInfo"
import Deploying from "@/components/deploying"
import Loading from "@/components/loading"
import DeleteTemplateModal from "./DeleteTemplateModal"
import { useDeployments } from "@/contexts/DeploymentContext"

// Type definitions for template management
interface Template {
  id: string
  name: string
  description: string
  created: string
  parameters: any
}

interface Topology {
  nodes: any[]
  edges: any[]
  usedIPs: Set<string>
  credentials?: {
    enterpriseAdminUsername: string
    enterpriseAdminPassword: string
  }
}

interface CustomNode extends Node {
  id: string
  position: { x: number; y: number }
  data: {
    domainName?: string
    domainControllerName?: string
    workstationName?: string
    privateIPAddress: string
    adminUsername?: string
    adminPassword?: string
    isSub?: boolean
  }
}

// Password validation function
const validatePassword = (password: string): boolean => {
  if (password.length < 8 || password.length > 123) return false

  let complexity = 0
  if (/[A-Z]/.test(password)) complexity++ // Has uppercase
  if (/[a-z]/.test(password)) complexity++ // Has lowercase
  if (/[0-9]/.test(password)) complexity++ // Has digit
  if (/[^A-Za-z0-9]/.test(password)) complexity++ // Has special char

  return complexity >= 3
}

// Node definition components
const nodeTypes = {
  domainController: ({ data }: { data: any }) => (
    <div
      className={`p-4 rounded-xl shadow-2xl relative border backdrop-blur-sm ${
        data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
      } ${
        data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900" : ""
      } ${
        data.isSub
          ? "bg-gradient-to-br from-purple-600 to-violet-700 shadow-purple-900/50 border-purple-500/30"
          : "bg-gradient-to-br from-pink-600 to-rose-700 shadow-pink-900/50 border-pink-500/30"
      } text-white`}
    >
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
        position="right"
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
        position="left"
        id="target"
        style={{
          background: "#fff",
          width: 12,
          height: 12,
          border: data.isSub ? "2px solid #9333ea" : "2px solid #ec4899",
        }}
      />
    </div>
  ),
  workstation: ({ data }: { data: any }) => (
    <div className={`bg-gradient-to-br from-emerald-600 to-teal-700 text-white p-4 rounded-xl shadow-2xl shadow-emerald-900/50 relative border border-emerald-500/30 backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    } ${
      data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900" : ""
    }`}>
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
      <strong className="text-sm font-bold">Workstation</strong>
      <div className="text-xs mt-2 space-y-1">
        <div className="font-semibold">{data.workstationName}</div>
        <div className="text-emerald-100">{data.domainName || ""}</div>
        <div className="text-emerald-200">IP: {data.privateIPAddress}</div>
      </div>
      <Handle
        type="target"
        position="left"
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
        position="right"
        id="source"
        style={{
          background: "#fff",
          width: 12,
          height: 12,
          border: "2px solid #10b981",
        }}
      />
    </div>
  ),
  jumpbox: ({ data }: { data: any }) => (
    <div className={`bg-gradient-to-br from-orange-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-orange-900/50 relative border border-orange-400/30 backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    }`}>
      {data.locked && (
        <div className="absolute -top-2 -right-2 bg-yellow-500 text-black rounded-full w-6 h-6 flex items-center justify-center text-xs">
          🔒
        </div>
      )}
      {/* Jumpbox always has public IP by nature */}
      <div className="absolute -top-2 -left-2 bg-cyan-400 text-black rounded-full px-2 py-0.5 text-xs font-bold">
        Public IP
      </div>
      <strong className="text-sm font-bold">Jumpbox</strong>
      <div className="text-xs mt-2">
        <div className="text-orange-100">IP: {data.privateIPAddress}</div>
      </div>
      <Handle
        type="source"
        position="right"
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
        position="left"
        id="target"
        style={{
          background: "#fff",
          width: 12,
          height: 12,
          border: "2px solid #f97316",
        }}
      />
    </div>
  ),
  certificateAuthority: ({ data }: { data: any }) => (
    <div className={`bg-gradient-to-br from-yellow-500 to-amber-600 text-white p-4 rounded-xl shadow-2xl shadow-yellow-900/50 relative border border-yellow-400/30 backdrop-blur-sm ${
      data.locked ? "opacity-75 ring-2 ring-yellow-500" : ""
    } ${
      data.hasPublicIP ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900" : ""
    }`}>
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
      <Handle
        type="target"
        position="left"
        id="target"
        style={{
          background: "#fff",
          width: 12,
          height: 12,
          border: "2px solid #eab308",
        }}
      />
    </div>
  ),
}

// Simple Dialog component
const Dialog: React.FC<{
  open: boolean
  onClose: () => void
  children: React.ReactNode
}> = ({ open, onClose, children }) => {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

// IP address utility functions
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

// Check if a domain is a subdomain of another
const isSubdomainOf = (subdomain: string, parentDomain: string): boolean => {
  if (subdomain === parentDomain) return false
  return subdomain.endsWith("." + parentDomain)
}

// Enhanced Template Gallery component
const TemplateGallery: React.FC<{
  templates: Template[]
  selectedTemplateId: string | null
  onSelect: (template: Template) => void
  onOpenTemplateManager: () => void
}> = ({ templates, selectedTemplateId, onSelect, onOpenTemplateManager }) => {
  const [searchTerm, setSearchTerm] = useState("")
  const [page, setPage] = useState(0)
  const templatesPerPage = 3

  const filteredTemplates = templates.filter(
    (template) =>
      template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      template.description.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const paginatedTemplates = filteredTemplates.slice(
    page * templatesPerPage,
    (page + 1) * templatesPerPage
  )

  const pageCount = Math.ceil(filteredTemplates.length / templatesPerPage)

  return (
    <div className="w-full mb-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="heading-md">Templates</h2>

        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search templates..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value)
              setPage(0) // Reset to first page on search
            }}
            className="bg-base-100/50 border border-base-300 rounded-lg px-3 py-2 text-sm focus:border-primary focus:ring-2 focus:ring-primary/20 focus:outline-none transition-all"
          />

          {templates.length > 3 && (
            <button
              type="button"
              onClick={onOpenTemplateManager}
              className="text-sm text-primary hover:text-primary"
            >
              View All ({templates.length})
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
        {paginatedTemplates.map((template) => (
          <div
            key={template.id}
            className={
              selectedTemplateId === template.id
                ? "template-card-selected"
                : "template-card"
            }
            onClick={() => onSelect(template)}
          >
            <h3 className="font-bold text-lg text-base-content">
              {template.name}
            </h3>
            <p className="text-sm text-base-content/60">{template.description}</p>
            <div className="mt-2 text-xs text-base-content0">
              Created: {new Date(template.created).toLocaleDateString()}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {template.parameters.rootDomainControllers?.value?.length > 0 && (
                <span className="template-tag-blue">
                  {template.parameters.rootDomainControllers.value.length} Root
                  DC
                </span>
              )}
              {template.parameters.subDomainControllers?.value?.length > 0 && (
                <span className="template-tag-purple">
                  {template.parameters.subDomainControllers.value.length} Sub DC
                </span>
              )}
              {template.parameters.standaloneServers?.value?.length > 0 && (
                <span className="template-tag-green">
                  {template.parameters.standaloneServers.value.length} Servers
                </span>
              )}
              {template.parameters.certificateAuthorities?.value?.length > 0 && (
                <span className="template-tag-orange">
                  {template.parameters.certificateAuthorities.value.length} CA
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Pagination controls */}
      {pageCount > 1 && (
        <div className="flex justify-center gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((prev) => Math.max(0, prev - 1))}
            className={`px-3 py-1 rounded-lg transition-all ${
              page === 0
                ? "bg-base-200/50 text-base-content0 cursor-not-allowed"
                : "bg-base-300 hover:bg-base-300 text-base-content/80"
            }`}
          >
            &lt;
          </button>

          <span className="text-sm px-3 py-1 text-base-content/60">
            Page {page + 1} of {pageCount}
          </span>

          <button
            disabled={page >= pageCount - 1}
            onClick={() => setPage((prev) => Math.min(pageCount - 1, prev + 1))}
            className={`px-3 py-1 rounded-lg transition-all ${
              page >= pageCount - 1
                ? "bg-base-200/50 text-base-content0 cursor-not-allowed"
                : "bg-base-300 hover:bg-base-300 text-base-content/80"
            }`}
          >
            &gt;
          </button>
        </div>
      )}
    </div>
  )
}

// Template manager modal component
const TemplateManager: React.FC<{
  open: boolean
  onClose: () => void
  templates: Template[]
  onSelect: (template: Template) => void
  onDelete: (template: Template) => Promise<void>
}> = ({ open, onClose, templates, onSelect, onDelete }) => {
  const [searchTerm, setSearchTerm] = useState("")
  const [sortBy, setSortBy] = useState<"name" | "created">("created")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [templateToDelete, setTemplateToDelete] = useState<Template | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const filteredTemplates = templates
    .filter(
      (template) =>
        template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        template.description.toLowerCase().includes(searchTerm.toLowerCase())
    )
    .sort((a, b) => {
      if (sortBy === "name") {
        return sortDir === "asc"
          ? a.name.localeCompare(b.name)
          : b.name.localeCompare(a.name)
      } else {
        return sortDir === "asc"
          ? new Date(a.created).getTime() - new Date(b.created).getTime()
          : new Date(b.created).getTime() - new Date(a.created).getTime()
      }
    })

  if (!open) return null

  return (
    <Dialog open={open} onClose={onClose}>
      <div className="bg-base-100/95 backdrop-blur-md p-6 rounded-xl border border-base-300/50 w-full max-w-4xl max-h-[80vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="template-manager-title">Template Manager</h2>
          <button
            onClick={onClose}
            className="text-base-content/60 hover:text-white transition-colors text-2xl"
          >
            &times;
          </button>
        </div>

        <div className="flex gap-4 mb-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder="Search templates..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-base-200/50 border border-base-300 rounded-lg px-3 py-2 focus:border-primary focus:ring-2 focus:ring-primary/20 focus:outline-none transition-all"
            />
          </div>

          <div className="flex gap-2">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "name" | "created")}
              className="bg-base-200/50 border border-base-300 rounded-lg px-3 py-2 focus:border-primary focus:outline-none transition-all"
            >
              <option value="name">Name</option>
              <option value="created">Date</option>
            </select>

            <button
              onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
              className="bg-base-300 hover:bg-base-300 border border-base-300 rounded-lg px-3 py-2 transition-all"
            >
              {sortDir === "asc" ? "↑" : "↓"}
            </button>
          </div>
        </div>

        <div className="grid gap-4">
          {filteredTemplates.map((template) => (
            <div
              key={template.id}
              className="p-4 border border-base-300/50 rounded-xl hover:border-primary transition-all duration-300 bg-base-200/30 backdrop-blur-sm hover:shadow-lg"
            >
              <div className="flex justify-between">
                <div>
                  <h3 className="font-bold text-lg text-base-content">
                    {template.name}
                  </h3>
                  <p className="text-sm text-base-content/60">
                    {template.description}
                  </p>
                </div>

                <div className="flex items-start gap-2">
                  <button
                    onClick={() => {
                      onSelect(template)
                      onClose()
                    }}
                    className="px-3 py-1 bg-primary hover:bg-primary rounded text-sm"
                  >
                    Load
                  </button>
                  <button
                    onClick={() => {
                      setTemplateToDelete(template)
                      setDeleteModalOpen(true)
                    }}
                    className="px-3 py-1 bg-error hover:bg-error/90 rounded text-sm"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="mt-2 text-xs text-base-content0">
                Created: {new Date(template.created).toLocaleDateString()}
              </div>

              <div className="mt-2 flex flex-wrap gap-1">
                {template.parameters.rootDomainControllers?.value?.length >
                  0 && (
                  <span className="px-2 py-1 bg-primary/50 text-primary rounded-full text-xs">
                    {template.parameters.rootDomainControllers.value.length}{" "}
                    Root DC
                  </span>
                )}
                {template.parameters.subDomainControllers?.value?.length >
                  0 && (
                  <span className="px-2 py-1 bg-purple-900/50 text-purple-300 rounded-full text-xs">
                    {template.parameters.subDomainControllers.value.length} Sub
                    DC
                  </span>
                )}
                {template.parameters.standaloneServers?.value?.length > 0 && (
                  <span className="px-2 py-1 bg-success/50 text-success rounded-full text-xs">
                    {template.parameters.standaloneServers.value.length} Servers
                  </span>
                )}
                {template.parameters.certificateAuthorities?.value?.length > 0 && (
                  <span className="px-2 py-1 bg-orange-900/50 text-orange-300 rounded-full text-xs">
                    {template.parameters.certificateAuthorities.value.length} CA
                  </span>
                )}
              </div>
            </div>
          ))}

          {filteredTemplates.length === 0 && (
            <div className="text-center py-8 text-base-content/60">
              No templates found matching your search.
            </div>
          )}
        </div>

        {/* Delete Template Modal */}
        <DeleteTemplateModal
          isOpen={deleteModalOpen}
          onClose={() => {
            setDeleteModalOpen(false)
            setTemplateToDelete(null)
          }}
          onConfirm={async () => {
            if (templateToDelete) {
              setIsDeleting(true)
              try {
                await onDelete(templateToDelete)
                setDeleteModalOpen(false)
                setTemplateToDelete(null)
              } catch (error) {
                console.error("Error deleting template:", error)
              } finally {
                setIsDeleting(false)
              }
            }
          }}
          templateName={templateToDelete?.name || ""}
        />
      </div>
    </Dialog>
  )
}

export default function BuildPage() {
  const router = useRouter()
  const { refreshDeployments } = useDeployments()
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const nodeIdCounter = useRef(1) // Counter for unique node IDs - only increments, never decreases
  const edgeIdCounter = useRef(1) // Counter for unique edge IDs - only increments, never decreases
  const [credentials, setCredentials] = useState({
    enterpriseAdminUsername: "",
    enterpriseAdminPassword: "",
  })
  const [scenarioInfo, setScenarioInfo] = useState("")
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
  const [isBuilding, setIsBuilding] = useState(false)
  const [envState, setEnvState] = useState<string | null>(null) // null = loading
  const [deploymentID, setDeploymentID] = useState("")
  const [buildStatus, setBuildStatus] = useState<string>("ready") // "ready", "building", "deployed", "error"
  const [pollCount, setPollCount] = useState(0)

  // Password validation state
  const [passwordError, setPasswordError] = useState("")

  // Template management state
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null
  )
  const [shouldApplyAutoLayout, setShouldApplyAutoLayout] = useState(false)
  const [showTemplateDialog, setShowTemplateDialog] = useState(false)
  const [showTemplateManager, setShowTemplateManager] = useState(false)
  const [templateName, setTemplateName] = useState("")
  const [templateDescription, setTemplateDescription] = useState("")
  const [fileUploadError, setFileUploadError] = useState("")

  // Update mode state - for updating existing saved scenarios
  const [isUpdateMode, setIsUpdateMode] = useState(false)
  const [baseScenario, setBaseScenario] = useState<string | null>(null)
  const [buildScenarios, setBuildScenarios] = useState<string[]>([])
  const [updateSessionDeploymentId, setUpdateSessionDeploymentId] = useState<string | null>(null)
  // Phases: "select" -> "select-deployment" -> "deploy-base" -> "add-nodes" -> "deploy-update" -> "test" -> "save"
  const [updatePhase, setUpdatePhase] = useState<"select" | "select-deployment" | "deploy-base" | "add-nodes" | "deploy-update" | "test" | "save">("select")
  const [lockedNodeIds, setLockedNodeIds] = useState<Set<string>>(new Set())
  // Multiple deployments for same scenario
  const [existingDeployments, setExistingDeployments] = useState<Array<{deploymentId: string, location: string, tags: Record<string, string>}>>([])
  // Track original Jumpbox connection for detecting changes
  const [originalJumpboxConnection, setOriginalJumpboxConnection] = useState<string | null>(null)
  // Pending NSG cleanup - when Jumpbox moves to a NEW node, we need to remove rules from old node after deploy
  const [pendingNsgCleanup, setPendingNsgCleanup] = useState<{oldIP: string, newIP: string, jumpboxIP: string} | null>(null)

  // Save blocker - dynamic timer based on topology complexity after deployment
  const [deploymentStartTime, setDeploymentStartTime] = useState<number | null>(null)
  const [saveBlockerRemaining, setSaveBlockerRemaining] = useState<number>(0)
  const [saveBlockerDuration, setSaveBlockerDuration] = useState<number>(10 * 60 * 1000) // Default 10 minutes

  // Calculate dynamic save blocker duration based on nodes
  const calculateSaveBlockerDuration = useCallback((nodesToDeploy: any[]) => {
    const BASE_WAIT_MS = 10 * 60 * 1000 // 10 minutes base
    const MAX_WAIT_MS = 40 * 60 * 1000 // 40 minutes max
    
    // Count node types
    const subDcCount = nodesToDeploy.filter(n => 
      n.type === "domainController" && n.data?.isSub
    ).length
    const workstationCount = nodesToDeploy.filter(n => 
      n.type === "workstation" || n.type === "standalone"
    ).length
    const caCount = nodesToDeploy.filter(n => 
      n.type === "certificateAuthority"
    ).length
    
    // Calculate additional wait: 3 min per sub-DC, 2 min per workstation/CA
    const additionalWait = (subDcCount * 3 * 60 * 1000) + 
                          (workstationCount * 2 * 60 * 1000) + 
                          (caCount * 2 * 60 * 1000)
    
    return Math.min(BASE_WAIT_MS + additionalWait, MAX_WAIT_MS)
  }, [])

  // Generate a default description based on current topology nodes
  const generateDefaultDescription = useCallback(() => {
    const components: string[] = []

    // Count root DCs and sub DCs
    const rootDcCount = nodes.filter(
      (n) => n.type === "domainController" && !n.data?.isSub
    ).length
    const subDcCount = nodes.filter(
      (n) => n.type === "domainController" && n.data?.isSub
    ).length

    if (rootDcCount > 0) {
      components.push(`${rootDcCount} Root DC${rootDcCount > 1 ? "s" : ""}`)
    }
    if (subDcCount > 0) {
      components.push(`${subDcCount} Sub DC${subDcCount > 1 ? "s" : ""}`)
    }

    // Count CAs
    const caCount = nodes.filter((n) => n.type === "certificateAuthority").length
    if (caCount > 0) {
      components.push(`${caCount} CA${caCount > 1 ? "s" : ""}`)
    }

    // Count workstations/servers
    const workstationCount = nodes.filter(
      (n) => n.type === "workstation" || n.type === "standalone"
    ).length
    if (workstationCount > 0) {
      components.push(`${workstationCount} Server${workstationCount > 1 ? "s" : ""}`)
    }

    // Check for jumpbox
    const hasJumpbox = nodes.some((n) => n.type === "jumpbox")
    if (hasJumpbox) {
      components.push("1 Jumpbox")
    }

    return components.length > 0 ? components.join(", ") : ""
  }, [nodes])

  // Inline deployment progress for update mode
  const [updateDeploymentItems, setUpdateDeploymentItems] = useState<Array<{name: string, status: "running" | "succeeded" | "failed" | "pending"}>>([])
  const [isUpdateDeploying, setIsUpdateDeploying] = useState(false)


  // Custom node change handler that prevents deletion of locked nodes
  const handleNodesChange = useCallback((changes: any[]) => {
    // Filter out remove changes for locked nodes
    const filteredChanges = changes.filter((change) => {
      if (change.type === "remove" && lockedNodeIds.has(change.id)) {
        // Prevent deletion of locked nodes
        alert("Cannot delete locked nodes from the base scenario.")
        return false
      }
      return true
    })
    onNodesChange(filteredChanges)
  }, [onNodesChange, lockedNodeIds])

  const handleEdgesChange = useCallback((changes: any[]) => {
    // In update mode, allow edge deletion (especially for repositioning jumpbox)
    // Edges are not locked like nodes - they can be deleted and reconnected freely
    
    // Log edge changes for debugging
    
    // Apply the changes normally
    onEdgesChange(changes)
  }, [onEdgesChange, edges])

  // Fetch deployment state without causing re-renders in a loop
  const fetchDeploymentState = useCallback(async (deploymentID: string) => {
    try {
      const response = await fetch(GlobalConfig.getDeploymentStateEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          deploymentID: deploymentID,
        }),
      })
      if (!response.ok) throw new Error("Failed to fetch deployment state")
      const data = await response.json()
      return data.message
    } catch (err) {
      console.error("Error fetching deployment state:", err)
      return null
    }
  }, [])

  // Auto-layout function for arranging nodes in a hierarchical pattern
  const autoLayout = useCallback(() => {
    // Skip if no nodes
    if (nodes.length === 0) return

    // First identify all node types
    const rootDCs = nodes.filter(
      (node) => node.type === "domainController" && !node.data.isSub
    )
    const subDCs = nodes.filter(
      (node) => node.type === "domainController" && node.data.isSub
    )
    const workstations = nodes.filter((node) => node.type === "workstation")
    const jumpboxes = nodes.filter((node) => node.type === "jumpbox")
    const cas = nodes.filter((node) => node.type === "certificateAuthority")

    // Build hierarchy map for multi-level domains
    const domainMap = new Map<string, Node>()
    const childrenMap = new Map<string, CustomNode[]>()

    // Map domain names to nodes
    ;[...rootDCs, ...subDCs].forEach((dc) => {
      domainMap.set(dc.data.domainName, dc)
    })

    // For each DC, find its children and organize them
    ;[...rootDCs, ...subDCs].forEach((dc) => {
      const children: Node[] = []

      // Find child DCs (subdomains)
      const childDCs = subDCs.filter(
        (subDC) =>
          isSubdomainOf(subDC.data.domainName, dc.data.domainName) &&
          // Make sure it's a direct child, not a grandchild
          subDC.data.domainName.split(".").length ===
            dc.data.domainName.split(".").length + 1
      )

      // Find workstations belonging to this domain
      const domainWorkstations = workstations.filter(
        (ws) => ws.data.domainName === dc.data.domainName
      )

      // Find CAs connected to this DC (CAs connect to root DCs only)
      const connectedCAs = cas.filter((ca) => {
        // Check if there's an edge connecting this CA to this DC
        return edges.some(
          (edge) =>
            (edge.source === dc.id && edge.target === ca.id) ||
            (edge.source === ca.id && edge.target === dc.id)
        )
      })

      // Combine all children
      children.push(...childDCs, ...domainWorkstations, ...connectedCAs)

      if (children.length > 0) {
        childrenMap.set(dc.id, children as CustomNode[])
      }
    })

    // Now do the layout calculation - LEFT TO RIGHT horizontal layout
    const spacing = { x: 280, y: 150 }  // x = horizontal spacing between levels, y = vertical spacing between siblings
    const updatedNodes = [...nodes]

    // Start with root DCs on the left
    rootDCs.forEach((rootDC, index) => {
      rootDC.position = {
        x: 100,  // All root DCs start at the left
        y: 100 + index * spacing.y,  // Stack vertically if multiple root DCs
      }

      // Recursively position children to the right
      positionChildren(rootDC, 1, childrenMap)
    })

    // Position jumpboxes at the bottom right of the rightmost nodes
    const maxX = Math.max(...updatedNodes.map(n => n.position?.x || 0), 100)
    const maxY = Math.max(...updatedNodes.map(n => n.position?.y || 0), 100)
    jumpboxes.forEach((jumpbox, index) => {
      jumpbox.position = {
        x: maxX + spacing.x,
        y: 100 + index * spacing.y,
      }
    })

    function positionChildren(
      parent: CustomNode,
      depth: number,
      childrenMap: Map<string, CustomNode[]>
    ) {
      const children = childrenMap.get(parent.id) || []

      if (children.length === 0) return

      // Position children in a column to the right of their parent
      children.forEach((child, index) => {
        child.position = {
          x: parent.position.x + spacing.x,  // Move right for each level
          y: parent.position.y - ((children.length - 1) * spacing.y) / 2 + index * spacing.y,  // Center vertically around parent
        }

        // Recursively position this child's children
        positionChildren(child, depth + 1, childrenMap)
      })
    }

    // Update node positions
    setNodes([...updatedNodes])
  }, [nodes, edges, setNodes])

  // Convert parameters to topology with improved domain hierarchy
  const convertParametersToTopology = useCallback(
    (params: any): Topology => {
      const newNodes: any[] = []
      const newEdges: any[] = []
      const usedIPSet = new Set<string>()
      let nodeId = 1

      // Process root domain controllers
      if (params.rootDomainControllers?.value) {
        params.rootDomainControllers.value.forEach((dc: any) => {
          const id = `node-${nodeId++}`
          newNodes.push({
            id,
            type: "domainController",
            position: { x: Math.random() * 400, y: Math.random() * 400 },
            data: {
              domainControllerName: dc.name,
              domainName: dc.domainName,
              privateIPAddress: dc.privateIPAddress,
              adminUsername:
                params.enterpriseAdminUsername?.value ||
                credentials.enterpriseAdminUsername,
              adminPassword:
                params.enterpriseAdminPassword?.value ||
                credentials.enterpriseAdminPassword,
              isSub: false,
              hasPublicIP: dc.hasPublicIP || false,
            },
          })
          usedIPSet.add(dc.privateIPAddress)
        })
      }

      // Map of domain names to node IDs
      const domainMap: Record<string, string> = {}
      newNodes.forEach((node) => {
        if (node.type === "domainController") {
          domainMap[node.data.domainName] = node.id
        }
      })

      // Process subdomain controllers with improved parent-child relationships
      if (params.subDomainControllers?.value) {
        params.subDomainControllers.value.forEach((dc: any) => {
          const id = `node-${nodeId++}`
          const dcNode = {
            id,
            type: "domainController",
            position: { x: Math.random() * 400, y: Math.random() * 400 },
            data: {
              domainControllerName: dc.name,
              domainName: dc.domainName,
              privateIPAddress: dc.privateIPAddress,
              adminUsername:
                params.enterpriseAdminUsername?.value ||
                credentials.enterpriseAdminUsername,
              adminPassword:
                params.enterpriseAdminPassword?.value ||
                credentials.enterpriseAdminPassword,
              isSub: true,
              hasPublicIP: dc.hasPublicIP || false,
            },
          }
          newNodes.push(dcNode)
          usedIPSet.add(dc.privateIPAddress)

          // Store this domain in the map
          domainMap[dc.domainName] = id
        })

        // After all DCs are processed, establish proper parent-child relationships
        newNodes
          .filter((node) => node.type === "domainController" && node.data.isSub)
          .forEach((node) => {
            const childDomain = node.data.domainName
            const domainParts = childDomain.split(".")
            let parentFound = false

            // Look for the most specific parent (immediate parent) first
            for (let i = 1; i < domainParts.length && !parentFound; i++) {
              const possibleParentDomain = domainParts.slice(i).join(".")
              const parentId = domainMap[possibleParentDomain]

              if (parentId && parentId !== node.id) {
                newEdges.push({
                  id: `edge-${edgeIdCounter.current++}`,
                  source: parentId,
                  target: node.id,
                })
                parentFound = true
              }
            }
          })
      }

      // Process standalone servers
      if (params.standaloneServers?.value) {
        params.standaloneServers.value.forEach((server: any) => {
          const id = `node-${nodeId++}`
          newNodes.push({
            id,
            type: "workstation",
            position: { x: Math.random() * 400, y: Math.random() * 400 },
            data: {
              workstationName: server.name,
              domainName: server.domainName, // Store domain name from params
              privateIPAddress: server.privateIPAddress,
              adminUsername:
                params.enterpriseAdminUsername?.value ||
                credentials.enterpriseAdminUsername,
              adminPassword:
                params.enterpriseAdminPassword?.value ||
                credentials.enterpriseAdminPassword,
              hasPublicIP: server.hasPublicIP || false,
            },
          })
          usedIPSet.add(server.privateIPAddress)
        })
      }

      // Connect workstations to their domain controllers based on domain membership
      newNodes
        .filter((node) => node.type === "workstation")
        .forEach((workstation) => {
          // Find the domain name this workstation belongs to
          const workstationDomain = workstation.data.domainName

          if (workstationDomain) {
            // Find a domain controller for this domain
            const domainController = newNodes.find(
              (node) =>
                node.type === "domainController" &&
                node.data.domainName === workstationDomain
            )

            if (domainController) {
              // Create connection between workstation and its domain controller
              newEdges.push({
                id: `edge-${edgeIdCounter.current++}`,
                source: domainController.id,
                target: workstation.id,
              })
            }
          }
        })

      // Add jumpbox if present in config
      if (params.jumpboxConfig?.value) {
        params.jumpboxConfig.value.forEach((jumpbox: any) => {
          const id = `node-${nodeId++}`
          const jumpboxNode = {
            id,
            type: "jumpbox",
            position: { x: Math.random() * 400, y: Math.random() * 400 },
            data: {
              privateIPAddress: jumpbox.jumpboxPrivateIPAddress,
            },
          }
          newNodes.push(jumpboxNode)
          usedIPSet.add(jumpbox.jumpboxPrivateIPAddress)

          // Find the connected node
          const connectedNodeId = newNodes.findIndex(
            (n) => n.data.privateIPAddress === jumpbox.connectedPrivateIPAddress
          )

          if (connectedNodeId >= 0) {
            newEdges.push({
              id: `edge-${edgeIdCounter.current++}`,
              source: newNodes[connectedNodeId].id,
              target: id,
            })
          }
        })
      }

      // Add Certificate Authorities if present
      if (params.certificateAuthorities?.value) {
        params.certificateAuthorities.value.forEach((ca: any) => {
          const id = `node-${nodeId++}`
          const caNode = {
            id,
            type: "certificateAuthority",
            position: { x: Math.random() * 400, y: Math.random() * 400 },
            data: {
              caName: ca.name,
              domainName: ca.domainName,
              privateIPAddress: ca.privateIPAddress,
              rootDomainControllerPrivateIp: ca.rootDomainControllerPrivateIp,
              hasPublicIP: ca.hasPublicIP || false,
            },
          }
          newNodes.push(caNode)
          usedIPSet.add(ca.privateIPAddress)

          // Find the connected Root DC
          const connectedDC = newNodes.find(
            (n) => 
              n.type === "domainController" && 
              n.data.privateIPAddress === ca.rootDomainControllerPrivateIp
          )

          if (connectedDC) {
            newEdges.push({
              id: `edge-${edgeIdCounter.current++}`,
              source: connectedDC.id,
              target: id,
            })
          }
        })
      }

      // Set the edge type to be orthogonal for all edges
      const edgesWithStyle = newEdges.map((edge) => ({
        ...edge,
        type: "smoothstep",
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
      }))

      return {
        nodes: newNodes,
        edges: edgesWithStyle,
        usedIPs: usedIPSet,
        credentials: {
          enterpriseAdminUsername: params.enterpriseAdminUsername?.value || "",
          enterpriseAdminPassword: params.enterpriseAdminPassword?.value || "",
        },
      }
    },
    [credentials]
  )

  // Apply topology to current state
  const setTemplateFromTopology = useCallback(
    (topology: Topology) => {
      setNodes(topology.nodes)
      
      // Ensure all edges have proper unique IDs and correct handles
      const edgesWithIds = topology.edges.map((edge, index) => {
        // If edge already has a valid ID, keep it; otherwise assign a new one
        const edgeId = edge.id && typeof edge.id === 'string' ? edge.id : `edge-${index + 1}`
        
        // Find source and target nodes to determine if this is a jumpbox connection
        const sourceNode = topology.nodes.find((n) => n.id === edge.source)
        const targetNode = topology.nodes.find((n) => n.id === edge.target)
        
        // For jumpbox connections, source should use RIGHT handle, target uses default
        const isJumpboxConnection = targetNode?.type === "jumpbox"
        
        return {
          ...edge,
          id: edgeId,
          sourceHandle: isJumpboxConnection ? "right" : (edge.sourceHandle || undefined),
          targetHandle: edge.targetHandle || undefined
        }
      })
      setEdges(edgesWithIds)
      setUsedIPs(topology.usedIPs)

      // Update nodeIdCounter to be higher than any existing node ID to prevent collisions
      // when adding new nodes after loading a template
      let maxNodeId = 0
      topology.nodes.forEach((node) => {
        const match = node.id.match(/^node-(\d+)$/)
        if (match) {
          const nodeNum = parseInt(match[1], 10)
          if (nodeNum > maxNodeId) {
            maxNodeId = nodeNum
          }
        }
      })
      nodeIdCounter.current = maxNodeId + 1

      // Update edgeIdCounter to be higher than any existing edge ID to prevent collisions
      // when adding new edges after loading a template
      let maxEdgeId = 0
      edgesWithIds.forEach((edge) => {
        if (edge.id && typeof edge.id === 'string') {
          const match = edge.id.match(/^edge-(\d+)$/)
          if (match) {
            const edgeNum = parseInt(match[1], 10)
            if (edgeNum > maxEdgeId) {
              maxEdgeId = edgeNum
            }
          }
        }
      })
      edgeIdCounter.current = maxEdgeId + 1

      // Update available IPs based on selected range and used IPs
      if (selectedRange) {
        setAvailableIPs(
          ipRanges[selectedRange].filter((ip) => !topology.usedIPs.has(ip))
        )
      }

      // If template includes credentials, update them
      if (topology.credentials) {
        setCredentials(topology.credentials)
      }
    },
    [selectedRange, setNodes, setEdges]
  )

  // Check deployment state on mount - Fixed to prevent infinite loop
  useEffect(() => {
    const checkDeploymentState = async () => {
      const savedDeploymentID = GetCookie("deploymentID")
      if (savedDeploymentID && savedDeploymentID !== "error") {

        // Only check state for build deployments
        // Regular deployments from Deploy page should be left alone
        if (savedDeploymentID.startsWith("BuildLab-")) {
          setDeploymentID(savedDeploymentID)
          const state = await fetchDeploymentState(savedDeploymentID)

          if (state === "deployed") {
            setEnvState("deployed")
            setBuildStatus("deployed")
          } else if (state === "deploying") {
            setEnvState("deploying")
            setBuildStatus("building")
          } else {
            // State is null/initializing during Kali checks and Bicep compilation
            // Keep the cookie! Just show it's building
            setEnvState("deploying")
            setBuildStatus("building")
          }
        } else {
          // Non-build deployment - don't interfere with it, just reset build page state
          setEnvState("noDeployment")
          setBuildStatus("ready")
        }
      } else {
        setEnvState("noDeployment")
        setBuildStatus("ready")
      }
    }
    checkDeploymentState()
  }, [fetchDeploymentState])

  // Apply auto-layout only when explicitly requested
  useEffect(() => {
    if (shouldApplyAutoLayout) {
      // Use a slightly longer timeout to ensure React has finished updating nodes state
      const timeoutId = setTimeout(() => {
        autoLayout()
        setShouldApplyAutoLayout(false)
      }, 150)
      return () => clearTimeout(timeoutId)
    }
  }, [shouldApplyAutoLayout, autoLayout])

  // Load templates on component mount
  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const response = await fetch(GlobalConfig.getTemplatesEndpoint)
        if (!response.ok) throw new Error("Failed to fetch templates")
        const data = await response.json()
        setTemplates(data.templates || [])
      } catch (err) {
        console.error("Error fetching templates:", err)
      }
    }
    fetchTemplates()
  }, [])

  // Check deployment status periodically when building
  useEffect(() => {
    if (buildStatus === "building" && deploymentID) {

      const pollBuildStatus = async () => {
        setPollCount((prev) => prev + 1)

        const state = await fetchDeploymentState(deploymentID)

        if (state === "deployed") {
          setBuildStatus("deployed")
          setEnvState("deployed")

          // Handle update mode differently
          if (isUpdateMode && (updatePhase === "deploy-base" || updatePhase === "deploy-update")) {
            // Transition to next phase
            if (updatePhase === "deploy-base") {
              setUpdatePhase("add-nodes")
              // Reload the page to show the build UI
              setEnvState("noDeployment")
              setBuildStatus("ready")
            } else if (updatePhase === "deploy-update") {
              setUpdatePhase("test")
              // Don't redirect, let user test and save
              setEnvState("deployed")
            }
          } else {
            // Normal build mode - redirect to home
            setTimeout(() => {
              router.push("/")
            }, 1000)
          }
        } else if (state !== "deploying") {
          setBuildStatus("error")
        }
      }

      // Poll immediately first
      pollBuildStatus()

      // Increased from 10 seconds to 1 minute to reduce API calls
      const interval = setInterval(pollBuildStatus, 60000)
      return () => clearInterval(interval)
    }
  }, [buildStatus, deploymentID, router, fetchDeploymentState, isUpdateMode, updatePhase])

  // Save blocker timer - countdown based on dynamic duration after deployment completes
  useEffect(() => {
    if (!deploymentStartTime) {
      setSaveBlockerRemaining(0)
      return
    }

    const updateRemaining = () => {
      const elapsed = Date.now() - deploymentStartTime
      const remaining = Math.max(0, saveBlockerDuration - elapsed)
      setSaveBlockerRemaining(remaining)
    }

    // Update immediately
    updateRemaining()

    // Update every second
    const interval = setInterval(updateRemaining, 1000)
    return () => clearInterval(interval)
  }, [deploymentStartTime, saveBlockerDuration])

  // Fetch update deployment progress inline (without redirecting to Deploying page)
  useEffect(() => {
    if (!isUpdateMode || !isUpdateDeploying || !updateSessionDeploymentId) return

    const fetchUpdateProgress = async () => {
      try {
        const response = await fetch(GlobalConfig.getDeploymentStateEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ deploymentID: updateSessionDeploymentId }),
        })
        
        if (!response.ok) return
        
        const data = await response.json()
        const details = data.details || {}
        
        // Build unified list of all deployments with their statuses
        const allItems: Array<{name: string, status: "running" | "succeeded" | "failed" | "pending"}> = []
        const seenNames = new Set<string>();
        
        // Add failed deployments
        (details.failed || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "failed" })
          }
        });
        
        // Add running deployments
        (details.running || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "running" })
          }
        });
        
        // Add succeeded deployments
        (details.succeeded || []).forEach((name: string) => {
          if (!seenNames.has(name)) {
            seenNames.add(name)
            allItems.push({ name, status: "succeeded" })
          }
        });
        
        // Sort: running first, then succeeded, then failed
        allItems.sort((a, b) => {
          const order = { running: 0, succeeded: 1, failed: 2, pending: 3 }
          return order[a.status] - order[b.status]
        })
        
        setUpdateDeploymentItems(allItems)
        
        // Check if deployment is complete
        if (data.message === "deployed") {
          setIsUpdateDeploying(false)
          // Start save blocker timer when deployment completes
          setDeploymentStartTime(Date.now())
          
          // If there's pending NSG cleanup (Jumpbox moved to NEW node), update NSG rules now
          // This: 1) removes rules from old node, 2) updates Jumpbox's own NSG to new target
          if (pendingNsgCleanup) {
            try {
              await fetch(GlobalConfig.updateJumpboxConnectionEndpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  deploymentID: updateSessionDeploymentId,
                  oldConnectedIP: pendingNsgCleanup.oldIP,
                  newConnectedIP: pendingNsgCleanup.newIP, // Pass new IP to update Jumpbox's NSG
                  jumpboxIP: pendingNsgCleanup.jumpboxIP,
                  // Don't use removeOnly - we want to update Jumpbox's own NSG too
                }),
              })
            } catch (error) {
              console.error("Error updating NSG rules:", error)
            }
            setPendingNsgCleanup(null)
          }
          
          if (updatePhase === "deploy-base") {
            setUpdatePhase("add-nodes")
          } else if (updatePhase === "deploy-update") {
            setUpdatePhase("test")
          }
        }
      } catch (error) {
        console.error("Error fetching update deployment progress:", error)
      }
    }

    // Poll immediately and every 5 seconds
    fetchUpdateProgress()
    const interval = setInterval(fetchUpdateProgress, 5000)
    return () => clearInterval(interval)
  }, [isUpdateMode, isUpdateDeploying, updateSessionDeploymentId, updatePhase, pendingNsgCleanup])

  const onConnect = useCallback(
    (params: {
      source: string | null
      target: string | null
      sourceHandle?: string | null
      targetHandle?: string | null
    }) => {
      if (!params.source || !params.target) return
      const sourceNode = nodes.find((n) => n.id === params.source)
      const targetNode = nodes.find((n) => n.id === params.target)

      if (!sourceNode || !targetNode) return alert("Invalid connection")

      // Check for existing connection
      const already = edges.some(
        (e) => e.source === params.source && e.target === params.target
      )
      if (already) return alert("Connection already exists.")

      // Add style for orthogonal edges
      const newEdgeConfig = {
        ...params,
        type: "smoothstep",
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
      }

      // Allow DC to DC connections with sub DC logic
      if (
        sourceNode.type === "domainController" &&
        targetNode.type === "domainController"
      ) {
        const updatedNodes = nodes.map((node) =>
          node.id === targetNode.id
            ? { ...node, data: { ...node.data, isSub: true } }
            : node
        )
        setNodes(updatedNodes)
        setEdges((eds) => addEdge(newEdgeConfig, eds))
      }
      // Allow DC to workstation connections
      else if (
        sourceNode.type === "domainController" &&
        targetNode.type === "workstation"
      ) {
        // Validate that workstation is on the same VNet as the DC
        const dcIP = sourceNode.data.privateIPAddress || ""
        const wsIP = targetNode.data.privateIPAddress || ""
        
        const getVNetPrefix = (ip: string) => {
          if (ip.startsWith("10.")) return "10"
          if (ip.startsWith("192.168.")) return "192"
          if (ip.startsWith("172.")) return "172"
          return null
        }
        
        const dcVNet = getVNetPrefix(dcIP)
        const wsVNet = getVNetPrefix(wsIP)
        
        // Workstation must always be on the same VNet as its parent DC
        if (dcVNet !== wsVNet) {
          return alert(
            `Invalid connection: Workstation must be on the same subnet as the Domain Controller.\n\n` +
            `DC "${sourceNode.data.domainControllerName || sourceNode.data.domainName}" is on VNet ${dcVNet} (${dcIP})\n` +
            `Workstation "${targetNode.data.workstationName || targetNode.id}" is on VNet ${wsVNet} (${wsIP})\n\n` +
            `Please use an IP address in the same range for the workstation.`
          )
        }
        
        // Update workstation to include domain information
        const updatedNodes = nodes.map((node) =>
          node.id === targetNode.id
            ? {
                ...node,
                data: { ...node.data, domainName: sourceNode.data.domainName },
              }
            : node
        )
        setNodes(updatedNodes)
        setEdges((eds) => addEdge(newEdgeConfig, eds))
      }
      // Allow DC or workstation to jumpbox connections (one-way only: node → jumpbox)
      else if (
        (sourceNode.type === "domainController" ||
          sourceNode.type === "workstation") &&
        targetNode.type === "jumpbox"
      ) {
        // Enforce direction: source must use 'source' handle, target must use 'target' handle
        // This ensures the edge is always: Node (right) → Jumpbox (left)
        if (params.sourceHandle !== "source") {
          return alert(
            "Invalid connection: Please connect from the RIGHT handle of the node to the Jumpbox.\n\n" +
            "Correct: Node (right dot) → Jumpbox (left dot)"
          )
        }
        setEdges((eds) => addEdge(newEdgeConfig, eds))
      }
      // Prevent reverse connection (jumpbox → node)
      else if (
        sourceNode.type === "jumpbox" &&
        (targetNode.type === "domainController" ||
          targetNode.type === "workstation")
      ) {
        return alert(
          "Invalid connection: Jumpbox must be connected FROM a node, not TO a node.\n\n" +
          "Correct: Node (right dot) → Jumpbox (left dot)\n" +
          "Please connect from the node's right handle to the Jumpbox."
        )
      }
      // Allow DC to CA connections - CA can ONLY connect to Root DC (not SubDC)
      else if (
        sourceNode.type === "domainController" &&
        targetNode.type === "certificateAuthority"
      ) {
        // Validate that CA is connecting to a Root DC, not a SubDC
        if (sourceNode.data.isSub) {
          return alert(
            `Invalid connection: Certificate Authority can only connect to a Root Domain Controller, not a Sub DC.\n\n` +
            `"${sourceNode.data.domainControllerName}" is a Sub DC. Please connect the CA to the Root DC instead.`
          )
        }
        
        // Update CA to include domain information from connected DC
        const updatedNodes = nodes.map((node) =>
          node.id === targetNode.id
            ? {
                ...node,
                data: { 
                  ...node.data, 
                  domainName: sourceNode.data.domainName,
                  rootDomainControllerPrivateIp: sourceNode.data.privateIPAddress
                },
              }
            : node
        )
        setNodes(updatedNodes)
        setEdges((eds) => addEdge(newEdgeConfig, eds))
      } else {
        alert(
          "Invalid connection. Only allowed connections are:\n- Domain Controller to Domain Controller\n- Domain Controller to Workstation\n- Domain Controller to Certificate Authority\n- Domain Controller/Workstation to Jumpbox"
        )
      }
    },
    [nodes, edges, setNodes, setEdges]
  )

  const addNode = useCallback(() => {
    if (!formData.privateIPAddress) {
      return alert("Please select an IP address.")
    }

    const newNode = {
      id: `node-${nodeIdCounter.current++}`,
      type: formData.type,
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data:
        formData.type === "domainController"
          ? {
              domainControllerName: formData.domainControllerName,
              domainName: formData.domainName,
              privateIPAddress: formData.privateIPAddress,
              adminUsername: credentials.enterpriseAdminUsername,
              adminPassword: credentials.enterpriseAdminPassword,
              isSub: false,
              hasPublicIP: formData.hasPublicIP,
            }
          : formData.type === "workstation"
          ? {
              workstationName: formData.workstationName,
              privateIPAddress: formData.privateIPAddress,
              adminUsername: credentials.enterpriseAdminUsername,
              adminPassword: credentials.enterpriseAdminPassword,
              hasPublicIP: formData.hasPublicIP,
            }
          : formData.type === "certificateAuthority"
          ? {
              caName: formData.caName,
              privateIPAddress: formData.privateIPAddress,
              hasPublicIP: formData.hasPublicIP,
            }
          : {
              privateIPAddress: formData.privateIPAddress,
            },
    }

    setNodes((nds) => [...nds, newNode])
    setUsedIPs((prev) => {
      const newSet = new Set(prev)
      newSet.add(formData.privateIPAddress)
      return newSet
    })
    setAvailableIPs((prev) =>
      prev.filter((ip) => ip !== formData.privateIPAddress)
    )
    setFormData({
      type: "domainController",
      domainControllerName: "",
      domainName: "",
      workstationName: "",
      caName: "",
      privateIPAddress: "",
      hasPublicIP: false,
    })
  }, [formData, nodes, credentials, setNodes])

  const handleRangeSelection = useCallback(
    (range: string) => {
      setSelectedRange(range)
      setAvailableIPs(ipRanges[range].filter((ip) => !usedIPs.has(ip)))
      setFormData((prev) => ({ ...prev, privateIPAddress: "" }))
    },
    [usedIPs]
  )

  // Template file upload handler
  const handleFileUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return

      // Reset error
      setFileUploadError("")

      // Check file type
      if (!file.name.endsWith(".json")) {
        setFileUploadError("Please upload a JSON file")
        return
      }

      try {
        const reader = new FileReader()
        reader.onload = (e: ProgressEvent<FileReader>) => {
          try {
            if (typeof e.target?.result !== "string") {
              setFileUploadError("Error reading file")
              return
            }

            const content = JSON.parse(e.target.result)

            // Basic validation
            if (!content.parameters) {
              setFileUploadError("Invalid template format")
              return
            }

            // Convert parameters to topology
            const topology = convertParametersToTopology(content.parameters)
            setTemplateFromTopology(topology)

            // Store template ID for highlighting in the UI
            setSelectedTemplateId(content.id || `template-${Date.now()}`)

            // Set flag to do auto-layout once
            setShouldApplyAutoLayout(true)
          } catch (err) {
            console.error("Error parsing JSON:", err)
            setFileUploadError("Invalid JSON format")
          }
        }
        reader.readAsText(file)
      } catch (err) {
        console.error("File upload error:", err)
        setFileUploadError("Error uploading file")
      }
    },
    [convertParametersToTopology, setTemplateFromTopology]
  )

  // Load a predefined template
  const loadTemplate = useCallback(
    (template: Template) => {
      try {
        const topology = convertParametersToTopology(template.parameters)
        setTemplateFromTopology(topology)

        // Store template ID for highlighting in the UI
        setSelectedTemplateId(template.id)

        // Set flag to do auto-layout once
        setShouldApplyAutoLayout(true)
      } catch (err) {
        console.error("Error loading template:", err)
        alert("Failed to load template")
      }
    },
    [convertParametersToTopology, setTemplateFromTopology]
  )

  // Delete a template
  const deleteTemplate = useCallback(async (template: Template) => {
    const response = await fetch(`${GlobalConfig.deleteTemplateEndpoint}/${template.id}`, {
      method: "DELETE",
    })
    if (!response.ok) {
      throw new Error("Failed to delete template")
    }
    // Remove from local state
    setTemplates((prev) => prev.filter((t) => t.id !== template.id))
  }, [])

  // Helper function to find domain for workstation based on connections
  const findDomainForWorkstation = useCallback(
    (workstationId: string): string | undefined => {
      // Find edge connecting workstation to DC
      const edge = edges.find(
        (e) =>
          e.target === workstationId &&
          nodes.find((n) => n.id === e.source && n.type === "domainController")
      )

      if (edge) {
        const dc = nodes.find((n) => n.id === edge.source) as {
          id: string
          data: { domainName: string }
        }
        return dc?.data.domainName
      }

      return undefined
    },
    [edges, nodes]
  )

  // Convert topology to parameters format for saving
  const convertTopologyToParameters = useCallback((): Record<string, any> => {
    const rootDCs: any[] = []
    const subDCs: any[] = []
    const servers: any[] = []
    const jumpboxConfig: any[] = []
    const caNodes: any[] = []

    // Process domain controllers
    nodes
      .filter((node) => node.type === "domainController")
      .forEach((node) => {
        const dcEntry = {
          name: node.data.domainControllerName,
          domainName: node.data.domainName,
          netbios: node.data.domainName.split(".")[0],
          isRoot: !node.data.isSub,
          privateIPAddress: node.data.privateIPAddress,
          hasPublicIP: node.data.hasPublicIP || false,
        }

        if (!node.data.isSub) {
          rootDCs.push(dcEntry)
        } else {
          subDCs.push(dcEntry)
        }
      })

    // Process workstations
    nodes
      .filter((node) => node.type === "workstation")
      .forEach((node) => {
        // Find domain from connections
        const domainName =
          node.data.domainName || findDomainForWorkstation(node.id)

        servers.push({
          name: node.data.workstationName,
          domainName: domainName,
          rootOrSub: "root", // Default to root if unknown
          privateIPAddress: node.data.privateIPAddress,
          hasPublicIP: node.data.hasPublicIP || false,
        })
      })

    // Process Certificate Authorities
    nodes
      .filter((node) => node.type === "certificateAuthority")
      .forEach((node) => {
        caNodes.push({
          name: node.data.caName,
          domainName: node.data.domainName,
          privateIPAddress: node.data.privateIPAddress,
          rootDomainControllerPrivateIp: node.data.rootDomainControllerPrivateIp,
          hasPublicIP: node.data.hasPublicIP || false,
        })
      })

    // Process jumpbox connections
    const jumpboxNodes = nodes.filter((node) => node.type === "jumpbox")

    jumpboxNodes.forEach((jumpboxNode) => {
      // Find connection to jumpbox
      const connectedEdge = edges.find(
        (edge) =>
          edge.source === jumpboxNode.id || edge.target === jumpboxNode.id
      )

      if (connectedEdge) {
        const connectedNodeId =
          connectedEdge.source === jumpboxNode.id
            ? connectedEdge.target
            : connectedEdge.source
        const connectedNode = nodes.find((n) => n.id === connectedNodeId)

        if (connectedNode) {
          jumpboxConfig.push({
            jumpboxPrivateIPAddress: jumpboxNode.data.privateIPAddress,
            connectedPrivateIPAddress: connectedNode.data.privateIPAddress,
          })
        }
      }
    })

    // Build parameters object
    return {
      deployResourceGroupName: { value: `BuildLab-Template` },
      scenarioSelection: { value: "BUILD" },
      location: { value: "eastus" },
      scenarioTagValue: { value: "BUILD" },
      expiryTimestamp: { value: new Date(Date.now() + 86400000).toISOString() }, // 24h from now
      enterpriseAdminUsername: { value: credentials.enterpriseAdminUsername },
      enterpriseAdminPassword: { value: credentials.enterpriseAdminPassword },
      subscriptionID: { value: "" },
      JUMPBOXImageReferenceID: {
        value: "",
      },
      rootDomainControllers: { value: rootDCs },
      subDomainControllers: { value: subDCs },
      standaloneServers: { value: servers },
      certificateAuthorities: { value: caNodes },
      jumpboxConfig: { value: jumpboxConfig },
    }
  }, [nodes, edges, credentials, findDomainForWorkstation])

  // Save current topology as a template
  const saveTemplate = useCallback(async () => {
    if (!templateName.trim()) {
      alert("Please provide a template name")
      return
    }

    // Validate that we have at least one domain controller
    const hasDomainController = nodes.some(
      (node) => node.type === "domainController"
    )
    if (!hasDomainController) {
      alert("Template must include at least one Domain Controller.")
      return
    }

    try {
      // Convert current topology to parameters format
      const parameters = convertTopologyToParameters()

      const templateData = {
        id: `template-${Date.now()}`,
        name: templateName,
        description: templateDescription,
        parameters,
        created: new Date().toISOString(),
      }

      const response = await fetch(GlobalConfig.saveTemplateEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(templateData),
      })

      if (!response.ok) throw new Error("Failed to save template")

      const result = await response.json()

      // Update local templates list
      setTemplates((prev) => [...prev, result.template])
      setShowTemplateDialog(false)
      setTemplateName("")
      setTemplateDescription("")

      alert("Template saved successfully")
    } catch (err) {
      console.error("Error saving template:", err)
      alert("Failed to save template")
    }
  }, [templateName, templateDescription, nodes, convertTopologyToParameters])

  // ===== UPDATE MODE FUNCTIONS =====

  // Fetch list of Build scenarios for update dropdown
  const fetchBuildScenarios = useCallback(async () => {
    try {
      const response = await fetch(GlobalConfig.listBuildScenariosEndpoint, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      })
      
      if (!response.ok) throw new Error("Failed to fetch scenarios")
      
      const data = await response.json()
      const scenarioNames = data.scenarios?.map((s: any) => s.name) || []
      setBuildScenarios(scenarioNames)
    } catch (err) {
      console.error("Error fetching build scenarios:", err)
      setBuildScenarios([])
    }
  }, [])

  // Load a scenario's topology for update mode
  const loadScenarioForUpdate = useCallback(async (scenarioName: string) => {
    try {
      const response = await fetch(GlobalConfig.getScenarioTopologyEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: scenarioName }),
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.error || "Failed to load scenario topology")
      }
      
      const data = await response.json()
      const topology = data.topology
      
      if (!topology || !topology.nodes) {
        throw new Error("Invalid topology data received")
      }
      
      // Set credentials from scenario (read-only in update mode)
      if (data.credentials) {
        setCredentials({
          enterpriseAdminUsername: data.credentials.enterpriseAdminUsername || "",
          enterpriseAdminPassword: data.credentials.enterpriseAdminPassword || "",
        })
      }
      
      // Check if this scenario has existing deployments
      const deployments = data.existingDeployments || []
      setExistingDeployments(deployments)
      
      // Count new (non-deployed) nodes in the topology
      const hasNewNodes = topology.nodes.some((node: any) => node.status === "new" || (!node.status && !node.data?.locked))
      
      if (deployments.length > 1) {
        // Multiple deployments exist - check if any have active update sessions
        const deploymentsWithActiveSession = deployments.filter((d: any) => d.hasActiveUpdateSession)
        if (deploymentsWithActiveSession.length === 1) {
          // One deployment has an active session - use that one
          const deployment = deploymentsWithActiveSession[0]
          setUpdateSessionDeploymentId(deployment.deploymentId)
          setDeploymentID(deployment.deploymentId)
          SetCookie("deploymentID", deployment.deploymentId)
          // If there are new nodes, go to test/save phase; otherwise add-nodes
          setUpdatePhase(hasNewNodes ? "test" : "add-nodes")
        } else {
          // Let user choose which deployment to update
          setUpdatePhase("select-deployment")
        }
      } else if (deployments.length === 1) {
        const deployment = deployments[0]
        setUpdateSessionDeploymentId(deployment.deploymentId)
        setDeploymentID(deployment.deploymentId)
        SetCookie("deploymentID", deployment.deploymentId)
        
        // If there's an active update session with new nodes, go to test phase
        if (deployment.hasActiveUpdateSession && hasNewNodes) {
          setUpdatePhase("test")
        } else {
          setUpdatePhase("add-nodes")
        }
      } else {
        // Scenario not deployed - need to deploy first
        setUpdatePhase("select")
      }
      
      // Mark DEPLOYED nodes as locked, but allow editing of NEW nodes (from update session)
      // EXCEPTION: Jumpbox is never locked - it can be repositioned as the entry point
      const lockedIds = new Set<string>()
      const loadedNodes = topology.nodes.map((node: any, index: number) => {
        // Jumpbox is never locked - it's the entry point and can be repositioned
        const isJumpbox = node.type === "jumpbox"
        // Only lock nodes that are already deployed (not new nodes from update session)
        // Jumpbox is an exception - always unlocked so user can reposition it
        const isDeployed = (node.status === "deployed" || node.data?.locked === true) && !isJumpbox
        if (isDeployed) {
          lockedIds.add(node.id)
        }
        return {
          ...node,
          // Ensure position exists - ReactFlow requires this
          position: node.position || { 
            x: 100 + (index % 3) * 250, 
            y: 100 + Math.floor(index / 3) * 200 
          },
          data: {
            ...node.data,
            locked: isDeployed, // Only mark deployed nodes as locked (Jumpbox excluded)
          },
        }
      })
      
      setLockedNodeIds(lockedIds)
      setNodes(loadedNodes)
      
      // Ensure all edges have proper unique IDs and correct handles
      const edgesWithIds = (topology.edges || []).map((edge: any, index: number) => {
        // If edge already has a valid ID, keep it; otherwise assign a new one
        const edgeId = edge.id && typeof edge.id === 'string' ? edge.id : `edge-${index + 1}`
        
        // Find source and target nodes to determine if this is a jumpbox connection
        const sourceNode = loadedNodes.find((n: any) => n.id === edge.source)
        const targetNode = loadedNodes.find((n: any) => n.id === edge.target)
        
        // For jumpbox connections, source should use RIGHT handle, target uses default
        const isJumpboxConnection = targetNode?.type === "jumpbox"
        
        return {
          ...edge,
          id: edgeId,
          sourceHandle: isJumpboxConnection ? "right" : (edge.sourceHandle || undefined),
          targetHandle: edge.targetHandle || undefined
        }
      })
      setEdges(edgesWithIds)
      
      // Update nodeIdCounter to be higher than any existing node ID to prevent collisions
      // when adding new nodes after loading a scenario for update
      let maxNodeId = 0
      loadedNodes.forEach((node: any) => {
        const match = node.id.match(/^node-(\d+)$/)
        if (match) {
          const nodeNum = parseInt(match[1], 10)
          if (nodeNum > maxNodeId) {
            maxNodeId = nodeNum
          }
        }
      })
      nodeIdCounter.current = maxNodeId + 1
      
      // Update edgeIdCounter to be higher than any existing edge ID to prevent collisions
      // when adding new edges after loading a scenario for update
      let maxEdgeId = 0
      edgesWithIds.forEach((edge: any) => {
        if (edge.id && typeof edge.id === 'string') {
          const match = edge.id.match(/^edge-(\d+)$/)
          if (match) {
            const edgeNum = parseInt(match[1], 10)
            if (edgeNum > maxEdgeId) {
              maxEdgeId = edgeNum
            }
          }
        }
      })
      edgeIdCounter.current = maxEdgeId + 1
      
      // Track original Jumpbox connection for detecting changes
      const jumpboxNode = loadedNodes.find((n: any) => n.type === "jumpbox")
      if (jumpboxNode) {
        const jumpboxEdge = (topology.edges || []).find((e: any) => 
          e.source === jumpboxNode.id || e.target === jumpboxNode.id
        )
        if (jumpboxEdge) {
          // Find the connected node's IP
          const connectedNodeId = jumpboxEdge.source === jumpboxNode.id ? jumpboxEdge.target : jumpboxEdge.source
          const connectedNode = loadedNodes.find((n: any) => n.id === connectedNodeId)
          if (connectedNode) {
            const connectedIP = connectedNode.data?.privateIPAddress || ""
            setOriginalJumpboxConnection(connectedIP)
          }
        }
      }
      
      // Update used IPs from existing nodes
      const usedIPsSet = new Set<string>()
      loadedNodes.forEach((node: any) => {
        if (node.data.privateIPAddress) {
          usedIPsSet.add(node.data.privateIPAddress)
        }
      })
      setUsedIPs(usedIPsSet)
      
      // Trigger auto-layout
      setShouldApplyAutoLayout(true)
      
    } catch (err) {
      console.error("Error loading scenario for update:", err)
      const errorMessage = err instanceof Error ? err.message : "Failed to load scenario topology"
      alert(`Error loading scenario: ${errorMessage}\n\nPlease check the browser console for details.`)
      
      // Reset state on error
      setNodes([])
      setEdges([])
      setLockedNodeIds(new Set())
      setBaseScenario(null)
    }
  }, [setNodes, setEdges])

  // Deploy base scenario before adding nodes
  const handleDeployBaseScenario = useCallback(async () => {
    if (!baseScenario) return
    
    setIsBuilding(true)
    setUpdatePhase("deploy-base")
    
    try {
      const response = await fetch(GlobalConfig.deployScenarioForUpdateEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: baseScenario }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || "Failed to deploy scenario")
      }
      
      const result = await response.json()
      const deploymentId = result.deploymentID
      
      // Store the deployment ID for future updates
      setUpdateSessionDeploymentId(deploymentId)
      SetCookie("deploymentID", deploymentId)
      setDeploymentID(deploymentId)
      
      // Note: Save blocker timer starts when deployment COMPLETES, not here
      
      // Start inline progress tracking (don't redirect to Deploying page)
      setIsUpdateDeploying(true)
      setUpdateDeploymentItems([])
      
      // Refresh deployments context
      await refreshDeployments()
      
    } catch (err) {
      console.error("Error deploying base scenario:", err)
      alert(`Failed to deploy base scenario: ${err instanceof Error ? err.message : String(err)}`)
      setUpdatePhase("select")
    } finally {
      setIsBuilding(false)
    }
  }, [baseScenario, refreshDeployments])

  // Handle selecting a specific deployment when multiple exist
  const handleSelectDeployment = useCallback((deploymentId: string) => {
    setUpdateSessionDeploymentId(deploymentId)
    setDeploymentID(deploymentId)
    SetCookie("deploymentID", deploymentId)
    setUpdatePhase("add-nodes")
  }, [])

  // Deploy update with new nodes
  const handleDeployUpdate = useCallback(async () => {
    if (!updateSessionDeploymentId || !baseScenario) return
    
    // Find jumpbox node (if any)
    const jumpboxNode = nodes.find((node) => node.type === "jumpbox")
    
    // Check if Jumpbox is NEW (added during this update session)
    // Jumpbox is NOT locked for repositioning, so we can't use lockedNodeIds
    // Instead, check if originalJumpboxConnection is set - if it is, Jumpbox existed in original scenario
    const isNewJumpbox = jumpboxNode && !originalJumpboxConnection
    
    // Get only the new (unlocked) nodes
    // Include NEW Jumpbox in newNodes for Bicep deployment
    // Exclude EXISTING Jumpbox (handled via NSG API, not redeployed)
    const newNodes = nodes.filter((node) => {
      if (lockedNodeIds.has(node.id)) return false  // Exclude locked/existing nodes
      if (node.type === "jumpbox" && !isNewJumpbox) return false  // Exclude existing Jumpbox (repositioning only)
      return true  // Include all other new nodes (including truly NEW Jumpbox)
    })
    
    // Get existing (locked) nodes for dependency resolution
    // ALSO include existing Jumpbox (not locked but should be preserved in topology)
    const existingNodes = nodes.filter((node) => {
      if (lockedNodeIds.has(node.id)) return true  // Locked nodes
      if (node.type === "jumpbox" && !isNewJumpbox) return true  // Existing Jumpbox (repositionable but not new)
      return false
    })
    // Get edges that involve new nodes
    const newEdges = edges.filter(
      (edge) => !lockedNodeIds.has(edge.source) || !lockedNodeIds.has(edge.target)
    )
    
    // Check if Jumpbox connection changed (only relevant for EXISTING jumpbox)
    let jumpboxConnectionChanged = false
    let newJumpboxConnectedIP = ""
    let isNewTargetANewNode = false  // Is the new Jumpbox target a NEW node being deployed?
    if (jumpboxNode && originalJumpboxConnection && !isNewJumpbox) {
      // Find current Jumpbox connection
      const jumpboxEdge = edges.find((e) => 
        e.source === jumpboxNode.id || e.target === jumpboxNode.id
      )
      if (jumpboxEdge) {
        const connectedNodeId = jumpboxEdge.source === jumpboxNode.id ? jumpboxEdge.target : jumpboxEdge.source
        const connectedNode = nodes.find((n) => n.id === connectedNodeId)
        if (connectedNode) {
          newJumpboxConnectedIP = connectedNode.data?.privateIPAddress || ""
          if (newJumpboxConnectedIP !== originalJumpboxConnection) {
            jumpboxConnectionChanged = true
            // Check if the new target is a new node (not locked) or existing node (locked)
            isNewTargetANewNode = !lockedNodeIds.has(connectedNodeId)
          }
        }
      }
    }
    
    // For NEW jumpbox, get the connected IP from edges
    if (isNewJumpbox && jumpboxNode) {
      const jumpboxEdge = edges.find((e) => 
        e.source === jumpboxNode.id || e.target === jumpboxNode.id
      )
      if (jumpboxEdge) {
        const connectedNodeId = jumpboxEdge.source === jumpboxNode.id ? jumpboxEdge.target : jumpboxEdge.source
        const connectedNode = nodes.find((n) => n.id === connectedNodeId)
        if (connectedNode) {
          newJumpboxConnectedIP = connectedNode.data?.privateIPAddress || ""
        }
      }
    }
    
    // If no new nodes AND no jumpbox change, nothing to deploy
    if (newNodes.length === 0 && !jumpboxConnectionChanged) {
      alert("No changes to deploy. Add nodes or reposition the Jumpbox first.")
      return
    }
    
    setIsBuilding(true)
    setUpdatePhase("deploy-update")
    
    try {
      const jumpboxIP = jumpboxNode?.data?.privateIPAddress || ""
      
      // Handle Jumpbox connection changes based on whether target is new or existing
      // Case 1: Target is EXISTING node - update NSG via API before deployment
      // Case 2: Target is NEW node - Bicep handles new node's NSG, but we need to remove from old after deploy
      
      if (jumpboxConnectionChanged && jumpboxNode && !isNewTargetANewNode) {
        // Target is an EXISTING node - update NSG rules now (before any deployment)
        
        const nsgResponse = await fetch(GlobalConfig.updateJumpboxConnectionEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            deploymentID: updateSessionDeploymentId,
            oldConnectedIP: originalJumpboxConnection,
            newConnectedIP: newJumpboxConnectedIP,
            jumpboxIP: jumpboxIP,
          }),
        })
        
        if (!nsgResponse.ok) {
          const error = await nsgResponse.json()
          throw new Error(error.error || "Failed to update Jumpbox NSG rules")
        }
        
        setOriginalJumpboxConnection(newJumpboxConnectedIP)
      }
      
      // If there are new nodes, deploy them
      if (newNodes.length > 0) {
        // Pass Jumpbox connection info to backend so it can set connectedPrivateIPAddress correctly
        // For NEW jumpbox, use newJumpboxConnectedIP; for existing, use changed or original
        const jumpboxConnectedIPToSend = isNewJumpbox 
          ? newJumpboxConnectedIP 
          : (jumpboxConnectionChanged ? newJumpboxConnectedIP : originalJumpboxConnection)
        
        const response = await fetch(GlobalConfig.deployUpdateEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            deploymentID: updateSessionDeploymentId,
            scenario: baseScenario,
            newNodes,
            newEdges,
            existingNodes,
            credentials,
            // Pass Jumpbox target so Bicep knows which node gets the Jumpbox NSG rules
            jumpboxConnectedIP: jumpboxConnectedIPToSend,
          }),
        })
        
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.error || "Failed to deploy update")
        }
        
        // Calculate dynamic save blocker duration based on nodes being deployed
        const dynamicDuration = calculateSaveBlockerDuration(newNodes)
        setSaveBlockerDuration(dynamicDuration)
        
        // Start inline progress tracking (don't redirect to Deploying page)
        setIsUpdateDeploying(true)
        setUpdateDeploymentItems([])
        
        // If Jumpbox moved to a NEW node, we need to update NSG rules AFTER deployment completes
        // This includes: 1) removing from old node, 2) updating Jumpbox's own NSG
        if (jumpboxConnectionChanged && isNewTargetANewNode && originalJumpboxConnection) {
          // Store this info so we can update NSG rules after deployment
          setPendingNsgCleanup({
            oldIP: originalJumpboxConnection,
            newIP: newJumpboxConnectedIP,
            jumpboxIP: jumpboxIP,
          })
        }
      } else if (jumpboxConnectionChanged && !isNewTargetANewNode) {
        // Only Jumpbox repositioned to existing node, no new nodes - go directly to test phase
        setUpdatePhase("test")
      } else {
        // This shouldn't happen based on our earlier check, but handle it
        setUpdatePhase("add-nodes")
      }
      
      // Update the original connection so subsequent updates work correctly
      if (jumpboxConnectionChanged) {
        setOriginalJumpboxConnection(newJumpboxConnectedIP)
      }
      
      // Note: Save blocker timer starts when deployment COMPLETES, not here
      
    } catch (err) {
      console.error("Error deploying update:", err)
      alert(`Failed to deploy update: ${err instanceof Error ? err.message : String(err)}`)
      setUpdatePhase("add-nodes")
    } finally {
      setIsBuilding(false)
    }
  }, [updateSessionDeploymentId, baseScenario, nodes, edges, lockedNodeIds, credentials, originalJumpboxConnection])

  // Save updated scenario with new images
  const handleSaveScenarioUpdate = useCallback(async () => {
    if (!updateSessionDeploymentId || !baseScenario) {
      alert("Missing deployment ID or scenario name")
      return
    }
    
    setIsBuilding(true)
    
    try {
      const response = await fetch(GlobalConfig.saveScenarioUpdateEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deploymentID: updateSessionDeploymentId,
          baseScenario: baseScenario,
        }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || "Failed to save scenario update")
      }
      
      const result = await response.json()
      alert(`Scenario updated successfully!\n\n${result.message || "Images captured and scenario saved."}`)
      
      // Reset update mode and redirect to home
      setIsUpdateMode(false)
      setBaseScenario(null)
      setUpdatePhase("select")
      setLockedNodeIds(new Set())
      setNodes([])
      setEdges([])
      
      // Redirect to home
      router.push("/")
      
    } catch (err) {
      console.error("Error saving scenario update:", err)
      alert(`Failed to save scenario update: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsBuilding(false)
    }
  }, [updateSessionDeploymentId, baseScenario, router, setNodes, setEdges])

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()

      // Validate password
      if (!validatePassword(credentials.enterpriseAdminPassword)) {
        setPasswordError(
          "Password must be 8-123 characters and meet at least 3 complexity requirements"
        )
        return alert("Please provide a valid enterprise admin password.")
      }

      const hasDomainController = nodes.some(
        (node) => node.type === "domainController"
      )
      if (!hasDomainController) {
        return alert("Topology must include at least one Domain Controller.")
      }

      const jumpboxNode = nodes.find((node) => node.type === "jumpbox")
      const hasNodeWithPublicIP = nodes.some(
        (node) => node.type !== "jumpbox" && (node.data as any)?.hasPublicIP === true
      )

      // Either a Jumpbox or at least one node with public IP is required
      if (!jumpboxNode && !hasNodeWithPublicIP) {
        return alert("Topology must include either a Jumpbox or at least one node with a Public IP.")
      }

      // If Jumpbox exists, it must be connected
      if (jumpboxNode) {
        const jumpboxEdge = edges.find(
          (edge) =>
            edge.source === jumpboxNode.id || edge.target === jumpboxNode.id
        )
        if (!jumpboxEdge) {
          return alert("Jumpbox must be connected to another node.")
        }
      }

      // Validate Certificate Authority (max 1, must connect to Root DC)
      const caNodes = nodes.filter((node) => node.type === "certificateAuthority")
      if (caNodes.length > 1) {
        return alert("Topology can only have one Certificate Authority.")
      }

      if (caNodes.length === 1) {
        const caNode = caNodes[0]
        const caEdge = edges.find(
          (edge) => edge.source === caNode.id || edge.target === caNode.id
        )

        if (!caEdge) {
          return alert("Certificate Authority must be connected to a Domain Controller.")
        }

        const connectedDCId = caEdge.source === caNode.id ? caEdge.target : caEdge.source
        const connectedDC = nodes.find((node) => node.id === connectedDCId)

        if (!connectedDC || connectedDC.type !== "domainController") {
          return alert("Certificate Authority must be connected to a Domain Controller.")
        }

        // Check if connected DC is a Root DC (not connected to another DC as child)
        const isRootDC = !edges.some(
          (edge) =>
            (edge.target === connectedDC.id) &&
            nodes.find((n) => n.id === edge.source && n.type === "domainController")
        )

        if (!isRootDC) {
          return alert("Certificate Authority must be connected to a Root Domain Controller only (not a Sub DC).")
        }
      }

      // Build jumpbox config only if jumpbox exists
      let jumpboxConfig: { privateIPAddress: string; connectedPrivateIPAddress: string } | null = null
      if (jumpboxNode) {
        const jumpboxEdge = edges.find(
          (edge) =>
            edge.source === jumpboxNode.id || edge.target === jumpboxNode.id
        )
        if (jumpboxEdge) {
          const connectedNodeId =
            jumpboxEdge.source === jumpboxNode.id
              ? jumpboxEdge.target
              : jumpboxEdge.source
          const connectedNode = nodes.find((node) => node.id === connectedNodeId)

          if (connectedNode) {
            jumpboxConfig = {
              privateIPAddress: jumpboxNode.data.privateIPAddress,
              connectedPrivateIPAddress: connectedNode.data.privateIPAddress,
            }
          }
        }
      }

      const topology = {
        credentials: {
          enterpriseAdminUsername: credentials.enterpriseAdminUsername,
          enterpriseAdminPassword: credentials.enterpriseAdminPassword,
        },
        nodes: nodes.map((node) => ({
          id: node.id,
          type: node.type,
          data: node.data,
        })),
        edges: edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle,
          targetHandle: edge.targetHandle,
        })),
        jumpboxConfig,
      }

      setIsBuilding(true)
      setBuildStatus("building")

      try {
        // Step 1: Generate deployment ID immediately and set cookie
        // This ensures the user stays associated with the deployment even if they navigate away
        const idResponse = await fetch(GlobalConfig.generateBuildIDEndpoint, {
          method: "POST",
        })

        if (!idResponse.ok) {
          throw new Error("Failed to generate deployment ID")
        }

        const idResult = await idResponse.json()
        const deploymentID = idResult.deploymentID

        if (!deploymentID) {
          throw new Error("Backend did not return a deployment ID")
        }

        // Set cookie immediately so user stays associated with deployment
        SetCookie("deploymentID", deploymentID)
        setDeploymentID(deploymentID)
        setEnvState("deploying")


        // Step 2: Now proceed with the full build (Kali check + Bicep compilation)
        const deploymentData = {
          deploymentID, // Include the generated ID so backend uses it
          topology,
          // Always send scenarioInfo - backend expects it
          // If empty, backend will generate descriptive text from topology
          scenarioInfo: scenarioInfo.trim(),
        }

        const response = await fetch(GlobalConfig.buildEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(deploymentData),
        })

        if (!response.ok) {
          const errorText = await response.text()
          console.error("Server response error:", errorText)
          throw new Error(
            `Failed to submit topology: ${response.status} ${response.statusText}\n${errorText}`
          )
        }

        const result = await response.json()

        // Refresh the deployment context immediately so it picks up the new deployment
        await refreshDeployments()
      } catch (err) {
        console.error("Submit Error:", err)
        alert(
          `Error submitting topology: ${
            err instanceof Error ? err.message : String(err)
          }`
        )
        setBuildStatus("error")
      } finally {
        setIsBuilding(false)
      }
    },
    [nodes, edges, credentials, validatePassword, scenarioInfo, refreshDeployments]
  )

  // Show loading while checking environment state
  if (envState === null) {
    return <Loading />
  }

  // For non-update mode, show the Deploying component when building
  if (!isUpdateMode && (buildStatus === "building" || envState === "deploying")) {
    return <Deploying customMessage="Building custom topology..." />
  }

  // Helper to format time remaining
  const formatTimeRemaining = (ms: number): string => {
    const minutes = Math.floor(ms / 60000)
    const seconds = Math.floor((ms % 60000) / 1000)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  // Check if save is blocked
  const isSaveBlocked = saveBlockerRemaining > 0

  return (
    <div className="page-container">
      <h1 className="base-title-centered base-text-color mb-4">
        Build Infrastructure
      </h1>

      {/* Mode Toggle - New Build vs Update Existing */}
      <div className="flex justify-center gap-4 mb-6">
        <button
          type="button"
          onClick={() => {
            setIsUpdateMode(false)
            setBaseScenario(null)
            setUpdatePhase("select")
            setLockedNodeIds(new Set())
            setNodes([])
            setEdges([])
          }}
          className={`px-6 py-3 rounded-lg font-semibold transition-all ${
            !isUpdateMode
              ? "bg-primary text-white shadow-lg"
              : "bg-base-300 text-base-content/80 hover:bg-base-300"
          }`}
        >
          New Build
        </button>
        <button
          type="button"
          onClick={() => {
            setIsUpdateMode(true)
            setSelectedTemplateId(null)
            setNodes([])
            setEdges([])
            // Fetch available scenarios when entering update mode
            fetchBuildScenarios()
          }}
          className={`px-6 py-3 rounded-lg font-semibold transition-all ${
            isUpdateMode
              ? "bg-purple-600 text-white shadow-lg"
              : "bg-base-300 text-base-content/80 hover:bg-base-300"
          }`}
        >
          Update Existing
        </button>
      </div>

      {/* Template Gallery - Only show in New Build mode */}
      {!isUpdateMode && (
        <>
          <TemplateGallery
            templates={templates}
            selectedTemplateId={selectedTemplateId}
            onSelect={loadTemplate}
            onOpenTemplateManager={() => setShowTemplateManager(true)}
          />

      {/* Template management buttons - Only in New Build mode */}
      <div className="flex gap-2 w-full mb-6 justify-end">
        {!isUpdateMode && (
          <>
            <label className="btn-danger cursor-pointer">
              Upload Template
              <input
                type="file"
                accept=".json"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
            <button
              type="button"
              onClick={() => setShowTemplateDialog(true)}
              className="btn-success"
            >
              Save Current Template
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => setShouldApplyAutoLayout(true)}
          className="btn-primary"
        >
          Auto-arrange Nodes
        </button>
      </div>
        </>
      )}

      {/* Update Mode - Scenario Selection */}
      {isUpdateMode && (
        <div className="form-section mb-6">
          <h3 className="form-section-title">Update Existing Scenario</h3>
          
          {/* Update Phase Indicator */}
          <div className="flex justify-center gap-2 mb-6">
            {["select", "deploy-base", "add-nodes", "deploy-update", "test", "save"].map((phase, index) => (
              <div
                key={phase}
                className={`flex items-center ${index > 0 ? "ml-2" : ""}`}
              >
                {index > 0 && <div className={`w-8 h-0.5 ${
                  ["select", "deploy-base", "add-nodes", "deploy-update", "test", "save"].indexOf(updatePhase) >= index
                    ? "bg-purple-500"
                    : "bg-base-300"
                }`} />}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                    updatePhase === phase
                      ? "bg-purple-600 text-white font-bold"
                      : ["select", "deploy-base", "add-nodes", "deploy-update", "test", "save"].indexOf(updatePhase) > ["select", "deploy-base", "add-nodes", "deploy-update", "test", "save"].indexOf(phase)
                        ? "bg-success text-white"
                        : "bg-base-300 text-base-content/60"
                  }`}
                >
                  {index + 1}
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-center gap-4 text-xs text-base-content/60 mb-6">
            <span>Select</span>
            <span>Deploy</span>
            <span>Add Nodes</span>
            <span>Update</span>
            <span>Test</span>
            <span>Save</span>
          </div>

          {/* Inline Deployment Progress - Show while deploying in update mode */}
          {isUpdateDeploying && (updatePhase === "deploy-base" || updatePhase === "deploy-update") && (
            <div className="bg-base-200 border border-base-300 rounded-lg p-4 mb-6">
              <h4 className="text-lg font-semibold text-base-content mb-3 flex items-center gap-2">
                <svg className="animate-spin h-5 w-5 text-purple-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                {updatePhase === "deploy-base" ? "Deploying Base Scenario..." : "Deploying Update..."}
              </h4>
              <p className="text-base-content/60 text-sm mb-4">
                Please wait while your infrastructure is being deployed. This may take several minutes.
              </p>
              
              {/* Deployment Items Progress */}
              {updateDeploymentItems.length > 0 && (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {updateDeploymentItems.map((item) => (
                    <div
                      key={item.name}
                      className={`flex items-center justify-between p-2 rounded ${
                        item.status === "succeeded" ? "bg-success/30 border border-success/50" :
                        item.status === "running" ? "bg-primary/30 border border-primary/50" :
                        item.status === "failed" ? "bg-error/30 border border-error/50" :
                        "bg-base-300/30 border border-base-300/50"
                      }`}
                    >
                      <span className="font-mono text-sm">{item.name}</span>
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
              )}
              
              {updateDeploymentItems.length === 0 && (
                <div className="text-base-content0 text-sm italic">
                  Initializing deployment...
                </div>
              )}
            </div>
          )}

          {/* Save Blocker Timer - Show when save is blocked */}
          {isSaveBlocked && updatePhase !== "deploy-base" && updatePhase !== "deploy-update" && (
            <div className="bg-yellow-900/30 border border-yellow-600/50 rounded-lg p-3 mb-4">
              <p className="text-yellow-200 text-sm flex items-center gap-2">
                <span className="text-lg">⏱️</span>
                <span>
                  Please wait <strong>{formatTimeRemaining(saveBlockerRemaining)}</strong> before saving. 
                  This ensures all services are properly initialized.
                </span>
              </p>
            </div>
          )}

          {/* Scenario Selection Dropdown */}
          <div className="mb-4">
            <label className="form-label">Select Scenario to Update</label>
            <select
              value={baseScenario || ""}
              onChange={(e) => {
                const scenarioName = e.target.value
                if (scenarioName) {
                  setBaseScenario(scenarioName)
                  loadScenarioForUpdate(scenarioName)
                } else {
                  setBaseScenario(null)
                  setNodes([])
                  setEdges([])
                  setLockedNodeIds(new Set())
                }
              }}
              className="form-select w-full"
              disabled={updatePhase !== "select"}
            >
              <option value="">-- Select a scenario --</option>
              {buildScenarios.map((scenario) => (
                <option key={scenario} value={scenario}>
                  {scenario}
                </option>
              ))}
            </select>
          </div>

          {/* Deploy Base Button - Only in select phase after scenario is chosen */}
          {updatePhase === "select" && baseScenario && nodes.length > 0 && (
            <div className="flex justify-center mt-4">
              <button
                type="button"
                onClick={handleDeployBaseScenario}
                className="btn-primary btn-large"
                disabled={isBuilding}
              >
                {isBuilding ? "Deploying..." : "Deploy Base Scenario"}
              </button>
            </div>
          )}

          {/* Select Deployment - When multiple deployments exist for the same scenario */}
          {updatePhase === "select-deployment" && existingDeployments.length > 1 && (
            <div className="bg-yellow-900/30 border border-yellow-600/50 rounded-lg p-4 mt-4">
              <p className="text-yellow-200 text-sm mb-3">
                <strong>Multiple deployments found.</strong> This scenario has been deployed to {existingDeployments.length} different resource groups. 
                Select which deployment you want to update:
              </p>
              <div className="space-y-2">
                {existingDeployments.map((deployment) => (
                  <button
                    key={deployment.deploymentId}
                    type="button"
                    onClick={() => handleSelectDeployment(deployment.deploymentId)}
                    className="w-full text-left p-3 bg-base-200 hover:bg-base-300 border border-base-300 rounded-lg transition-colors"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-cyan-400">{deployment.deploymentId}</span>
                      <span className="text-base-content/60 text-sm">{deployment.location}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Info about locked nodes */}
          {lockedNodeIds.size > 0 && (
            <div className="bg-purple-900/30 border border-purple-600/50 rounded-lg p-4 mt-4">
              <p className="text-purple-200 text-sm">
                <strong>Existing nodes are locked.</strong> You can add new nodes (workstations, sub-DCs, etc.) 
                but cannot modify or remove the {lockedNodeIds.size} existing node(s) from the base scenario.
                <br /><span className="text-purple-300 mt-1 inline-block">
                  <strong>Exception:</strong> The Jumpbox can be repositioned to set your new entry point.
                </span>
              </p>
            </div>
          )}

          {/* Add Nodes phase info */}
          {updatePhase === "add-nodes" && (
            <div className="bg-success/30 border border-success/50 rounded-lg p-4 mt-4">
              <p className="text-success-content text-sm">
                <strong>Base scenario deployed.</strong> You can now add new nodes using the form below.
                When ready, click "Deploy Update" to add the new nodes to the running environment.
              </p>
            </div>
          )}

          {/* Test phase info - after update deployment completes */}
          {updatePhase === "test" && (
            <div className="bg-primary/30 border border-primary/50 rounded-lg p-4 mt-4">
              <p className="text-primary-content text-sm">
                <strong>New nodes deployed.</strong> Your new nodes are now running in the environment.
                Test that everything works correctly, then click "Proceed to Save" to capture VM images
                and save the updated scenario permanently.
              </p>
            </div>
          )}

          {/* Save phase info */}
          {updatePhase === "save" && (
            <div className="bg-orange-900/30 border border-orange-600/50 rounded-lg p-4 mt-4">
              <p className="text-orange-200 text-sm">
                <strong>Ready to save.</strong> Click "Save Update to Scenario" to capture VM images for 
                the new nodes and update the scenario file. This will make the new nodes a permanent part 
                of the {baseScenario} scenario.
              </p>
            </div>
          )}
        </div>
      )}

      {fileUploadError && (
        <div className="text-error mb-4">{fileUploadError}</div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col w-full gap-6">
        <div className="form-section mb-6">
          <h3 className="form-section-title">Configuration</h3>

          {/* Hide credentials in update mode - they come from the saved scenario */}
          {!isUpdateMode && (
            <div className="responsive-two-col mb-4">
              <div>
                <label className="form-label">Enterprise Admin Username</label>
                <input
                  type="text"
                  value={credentials.enterpriseAdminUsername}
                  onChange={(e) =>
                    setCredentials({
                      ...credentials,
                      enterpriseAdminUsername: e.target.value,
                    })
                }
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">Enterprise Admin Password</label>
              <input
                type="password"
                value={credentials.enterpriseAdminPassword}
                onChange={(e) => {
                  const newPassword = e.target.value
                  setCredentials({
                    ...credentials,
                    enterpriseAdminPassword: newPassword,
                  })

                  if (newPassword && !validatePassword(newPassword)) {
                    setPasswordError(
                      "Password must be 8-123 characters and meet at least 3 complexity requirements"
                    )
                  } else {
                    setPasswordError("")
                  }
                }}
                className={passwordError ? "form-input-error" : "form-input"}
              />
              {passwordError && <p className="error-text">{passwordError}</p>}
              <p className="help-text">
                8-123 characters with at least 3 of: uppercase, lowercase,
                digit, special character
              </p>
            </div>
          </div>
          )}

          {/* Scenario description - also hide in update mode */}
          {!isUpdateMode && (
            <div className="mb-4">
              <label className="form-label">Scenario Description</label>
              <textarea
                value={scenarioInfo}
                onChange={(e) => {
                  setScenarioInfo(e.target.value)
                }}
                onBlur={(e) => {
                }}
                className="form-input"
                rows={3}
                placeholder="Enter a description for this scenario..."
              />
            </div>
          )}

          <h4 className="form-section-title text-base mb-3">
            Add Infrastructure Components
          </h4>

          {/* In update mode, show locked state message when not in add-nodes phase */}
          {isUpdateMode && updatePhase !== "add-nodes" && (
            <div className="bg-base-200/50 border border-base-300 rounded-lg p-4 mb-4">
              <div className="flex items-center gap-2 text-base-content/60">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m0 0v2m0-2h2m-2 0H9m3-10V4m0 0a4 4 0 00-4 4v1m4-5a4 4 0 014 4v1m-8 8h8a2 2 0 002-2v-3a2 2 0 00-2-2h-8a2 2 0 00-2 2v3a2 2 0 002 2z" />
                </svg>
                <span className="font-medium">
                  {updatePhase === "select" && "Deploy the base scenario first before adding nodes."}
                  {updatePhase === "select-deployment" && "Select which deployment to update first."}
                  {updatePhase === "deploy-base" && "Waiting for base scenario to deploy..."}
                  {updatePhase === "deploy-update" && "Waiting for update deployment to complete..."}
                  {updatePhase === "test" && "Testing phase - node configuration is locked."}
                  {updatePhase === "save" && "Save phase - node configuration is locked."}
                </span>
              </div>
            </div>
          )}

          <div className={`responsive-grid ${isUpdateMode && updatePhase !== "add-nodes" ? "opacity-50 pointer-events-none" : ""}`}>
            <div>
              <label className="form-label">Node Type</label>
              <select
                value={formData.type}
                onChange={(e) =>
                  setFormData({ ...formData, type: e.target.value })
                }
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
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        domainControllerName: e.target.value,
                      })
                    }
                    className="form-input"
                  />
                </div>
                <div>
                  <label className="form-label">Domain Name</label>
                  <input
                    type="text"
                    value={formData.domainName}
                    onChange={(e) =>
                      setFormData({ ...formData, domainName: e.target.value })
                    }
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
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      workstationName: e.target.value,
                    })
                  }
                  className="form-input"
                />
              </div>
            )}

            {formData.type === "certificateAuthority" && (
              <div>
                <label className="form-label">CA Name</label>
                <input
                  type="text"
                  value={formData.caName || ""}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      caName: e.target.value,
                    })
                  }
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
                  <option key={range} value={range}>
                    {range}
                  </option>
                ))}
              </select>
            </div>

            {selectedRange && (
              <div>
                <label className="form-label">IP Address</label>
                <select
                  value={formData.privateIPAddress}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      privateIPAddress: e.target.value,
                    })
                  }
                  className="form-select"
                >
                  <option value="">Select IP</option>
                  {availableIPs.map((ip) => (
                    <option key={ip} value={ip}>
                      {ip}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Public IP toggle - only show for non-jumpbox types */}
            {formData.type !== "jumpbox" && (
              <div className="flex items-center gap-3">
                <label className="form-label mb-0">Public IP</label>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.hasPublicIP}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        hasPublicIP: e.target.checked,
                      })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-base-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-base-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                  <span className="ml-2 text-sm text-base-content/80">
                    {formData.hasPublicIP ? "Yes" : "No"}
                  </span>
                </label>
              </div>
            )}

            <div className="flex items-end">
              <button
                type="button"
                onClick={addNode}
                className="btn-primary w-full"
                disabled={isUpdateMode && updatePhase !== "add-nodes"}
              >
                Add Node
              </button>
            </div>
          </div>
        </div>

        <div className="reactflow-container">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              type: "smoothstep",
              markerEnd: {
                type: MarkerType.ArrowClosed,
              },
            }}
            style={{ width: "100%", height: "100%" }}
          >
            <Controls />
            <Background />
          </ReactFlow>
        </div>

        <div className="flex justify-center pt-6 gap-4">
          {/* Show different buttons based on mode */}
          {!isUpdateMode ? (
            // New Build mode - normal submit
            <button 
              type="submit" 
              className={`btn-success btn-large ${isBuilding ? 'opacity-50 cursor-not-allowed' : ''}`}
              disabled={isBuilding}
            >
              {isBuilding ? (
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
                  Building...
                </span>
              ) : (
                "Submit Topology"
              )}
            </button>
          ) : (
            // Update mode - show context-appropriate button
            <>
              {updatePhase === "add-nodes" && (
                <button 
                  type="button"
                  onClick={handleDeployUpdate}
                  className={`btn-primary btn-large ${isBuilding ? 'opacity-50 cursor-not-allowed' : ''}`}
                  disabled={isBuilding || (() => {
                    // Check if there are any new nodes (excluding existing jumpbox)
                    const jumpboxNode = nodes.find(n => n.type === "jumpbox")
                    // Jumpbox is NEW only if there was no Jumpbox in the original scenario
                    const isNewJumpbox = jumpboxNode && !originalJumpboxConnection
                    
                    // Count new nodes - include NEW jumpbox, exclude EXISTING jumpbox
                    const newNodeCount = nodes.filter(n => {
                      if (lockedNodeIds.has(n.id)) return false
                      if (n.type === "jumpbox" && !isNewJumpbox) return false
                      return true
                    }).length
                    
                    if (newNodeCount > 0) return false  // Has new nodes, enable button
                    
                    // No new nodes - check if existing Jumpbox connection changed
                    if (jumpboxNode && originalJumpboxConnection && !isNewJumpbox) {
                      const jumpboxEdge = edges.find(e => e.source === jumpboxNode.id || e.target === jumpboxNode.id)
                      if (jumpboxEdge) {
                        const connectedNodeId = jumpboxEdge.source === jumpboxNode.id ? jumpboxEdge.target : jumpboxEdge.source
                        const connectedNode = nodes.find(n => n.id === connectedNodeId)
                        if (connectedNode) {
                          const newConnectedIP = connectedNode.data?.privateIPAddress || ""
                          if (newConnectedIP !== originalJumpboxConnection) return false  // Connection changed, enable
                        }
                      }
                    }
                    
                    return true  // Nothing to deploy, disable button
                  })()}
                >
                  {isBuilding ? (
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
                      Deploying Update...
                    </span>
                  ) : (() => {
                    const jumpboxNode = nodes.find(n => n.type === "jumpbox")
                    // Jumpbox is NEW only if there was no Jumpbox in the original scenario
                    const isNewJumpbox = jumpboxNode && !originalJumpboxConnection
                    
                    // Count new nodes - include NEW jumpbox in count
                    const newNodeCount = nodes.filter(n => {
                      if (lockedNodeIds.has(n.id)) return false
                      if (n.type === "jumpbox" && !isNewJumpbox) return false
                      return true
                    }).length
                    
                    // Check if existing Jumpbox connection changed
                    let existingJumpboxChanged = false
                    if (jumpboxNode && originalJumpboxConnection && !isNewJumpbox) {
                      const jumpboxEdge = edges.find(e => e.source === jumpboxNode.id || e.target === jumpboxNode.id)
                      if (jumpboxEdge) {
                        const connectedNodeId = jumpboxEdge.source === jumpboxNode.id ? jumpboxEdge.target : jumpboxEdge.source
                        const connectedNode = nodes.find(n => n.id === connectedNodeId)
                        if (connectedNode) {
                          const newConnectedIP = connectedNode.data?.privateIPAddress || ""
                          existingJumpboxChanged = newConnectedIP !== originalJumpboxConnection
                        }
                      }
                    }
                    
                    if (newNodeCount > 0 && existingJumpboxChanged) {
                      return `Deploy Update (${newNodeCount} nodes + Jumpbox moved)`
                    } else if (newNodeCount > 0) {
                      return `Deploy Update (${newNodeCount} new node${newNodeCount > 1 ? 's' : ''})`
                    } else if (existingJumpboxChanged) {
                      return "Apply Jumpbox Changes"
                    } else {
                      return "Deploy Update"
                    }
                  })()}
                </button>
              )}
              {updatePhase === "test" && (
                <button 
                  type="button"
                  onClick={() => setUpdatePhase("save")}
                  className="btn-success btn-large"
                >
                  Proceed to Save
                </button>
              )}
              {updatePhase === "save" && (
                <button 
                  type="button"
                  onClick={handleSaveScenarioUpdate}
                  className={`btn-success btn-large ${(isBuilding || isSaveBlocked) ? 'opacity-50 cursor-not-allowed' : ''}`}
                  disabled={isBuilding || isSaveBlocked}
                >
                  {isBuilding ? (
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
                      Saving & Capturing Images...
                    </span>
                  ) : isSaveBlocked ? (
                    <span className="flex items-center gap-2">
                      Wait {formatTimeRemaining(saveBlockerRemaining)} before saving
                    </span>
                  ) : (
                    "Save Updated Scenario"
                  )}
                </button>
              )}
            </>
          )}
        </div>
      </form>

      {/* Template Save Dialog */}
      {showTemplateDialog && (
        <Dialog
          open={showTemplateDialog}
          onClose={() => setShowTemplateDialog(false)}
        >
          <div className="bg-base-200 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Save Template</h2>
            <div className="mb-4">
              <label className="block mb-2">Template Name</label>
              <input
                type="text"
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                className="w-full bg-base-300 text-white p-2 rounded"
                placeholder="My Template"
              />
            </div>
            <div className="mb-4">
              <label className="block mb-2">Description</label>
              <textarea
                value={templateDescription}
                onChange={(e) => setTemplateDescription(e.target.value)}
                className="w-full bg-base-300 text-white p-2 rounded h-24"
                placeholder="Describe this template..."
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowTemplateDialog(false)}
                className="px-4 py-2 bg-base-300 text-white rounded"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveTemplate}
                className="px-4 py-2 bg-success text-white rounded"
              >
                Save Template
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Template Manager Dialog */}
      {showTemplateManager && (
        <TemplateManager
          open={showTemplateManager}
          onClose={() => setShowTemplateManager(false)}
          templates={templates}
          onSelect={loadTemplate}
          onDelete={deleteTemplate}
        />
      )}
    </div>
  )
}
