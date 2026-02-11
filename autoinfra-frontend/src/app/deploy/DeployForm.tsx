"use client"
import { Fragment, useState, useEffect, useRef } from "react"
import {
  Listbox,
  ListboxButton,
  ListboxOptions,
  ListboxOption,
  Transition,
} from "@headlessui/react"
import GlobalConfigs from "../app.config"
import { SetCookie } from "@/components/cookieHandler"
import DeleteScenarioModal from "./DeleteScenarioModal"

interface DeployFormProps {
  setValue: (value: string) => void;
  onDeploymentStarted?: () => void;
}

export default function DeployForm({ setValue, onDeploymentStarted }: DeployFormProps) {
  const [selected, setSelected] = useState("")
  const [isButtonDisabled, setButtonDisabled] = useState(false)
  const [scenarioData, setScenarioData] = useState<string[]>([])
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [availableVersions, setAvailableVersions] = useState<string[]>([])
  const [selectedVersion, setSelectedVersion] = useState<string>("")
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)

  // Per-machine version selection
  const [usePerMachineVersions, setUsePerMachineVersions] = useState(false)
  const [machineVersions, setMachineVersions] = useState<Record<string, string[]>>({})
  const [selectedMachineVersions, setSelectedMachineVersions] = useState<Record<string, string>>({})
  const [defaultMachineVersions, setDefaultMachineVersions] = useState<Record<string, string>>({})
  const [unifiedDCVersion, setUnifiedDCVersion] = useState<string>("")
  const [dcVersions, setDCVersions] = useState<string[]>([])

  const effectRan = useRef(false)

  // Build per-machine "latest" versions (each machine's newest version)
  const getLatestMachineVersions = (): Record<string, string> => {
    const latestVersions: Record<string, string> = {}
    for (const [machineName, versions] of Object.entries(machineVersions)) {
      // First version in the array is the latest (sorted descending)
      latestVersions[machineName] = versions[0] || "1.0.0"
    }
    return latestVersions
  }

  async function onSubmit(e: React.FormEvent) {
    setButtonDisabled(true)
    e.preventDefault()

    // Prepare request body with scenario and version info
    let requestBody: { scenario: string; version?: string; machineVersions?: Record<string, string> } = {
      scenario: selected,
    }

    if (usePerMachineVersions && Object.keys(selectedMachineVersions).length > 0) {
      // Use per-machine versions, but apply unified DC version to all DCs
      const finalMachineVersions = { ...selectedMachineVersions }

      // Apply unified DC version to all domain controllers
      if (unifiedDCVersion) {
        Object.keys(machineVersions).forEach(machineName => {
          if (isDomainController(machineName)) {
            finalMachineVersions[machineName] = unifiedDCVersion
          }
        })
      }

      requestBody.machineVersions = finalMachineVersions
    } else if (selectedVersion === "latest") {
      // "latest" means each machine gets its own latest version
      requestBody.machineVersions = getLatestMachineVersions()
    } else if (selectedVersion) {
      // Use unified version (same version for all machines)
      requestBody.version = selectedVersion
    }

    fetch(GlobalConfigs.deployEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    })
      .then((response) => response.json())
      .then((data) => {
        SetCookie("deploymentID", data.deploymentID)
        // Notify parent that deployment has started instead of reloading
        if (onDeploymentStarted) {
          onDeploymentStarted()
        } else {
          location.reload()
        }
      })
      .catch((error) => {
        console.error("Error Deploying", error)
        setButtonDisabled(false)
      })
  }

  async function getScenarios() {
    try {
      const response = await fetch(GlobalConfigs.listScenariosEndpoint)

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`)
      }

      const data = await response.json()

      // Ensure we always return an array
      if (data && data.message && Array.isArray(data.message)) {
        return data.message
      } else {
        return []
      }
    } catch (error) {
      console.error("Failed to load scenarios:", error)
      return []
    }
  }

  const updateInfoPanel = (newSelection: string) => {
    setValue(newSelection)
    setSelected(newSelection)

    // Fetch versions for Build- scenarios
    if (newSelection.startsWith("Build-")) {
      fetchVersions(newSelection)
    } else {
      // Clear versions for non-Build scenarios
      setAvailableVersions([])
      setSelectedVersion("")
      setMachineVersions({})
      setSelectedMachineVersions({})
      setDefaultMachineVersions({})
      setUsePerMachineVersions(false)
    }
  }

  const fetchVersions = async (scenario: string) => {
    setIsLoadingVersions(true)
    try {
      const response = await fetch(GlobalConfigs.getScenarioVersionsEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ scenario }),
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch versions: ${response.statusText}`)
      }

      const data = await response.json()
      const versions = data.versions || []

      // Add "latest" as the first option, then the unified versions
      const versionsWithLatest = ["latest", ...versions]
      setAvailableVersions(versionsWithLatest)
      setSelectedVersion("latest")  // Default to latest

      // Also extract per-machine versions from the same response
      // Backend returns: { machineVersions: { machineName: { versions: [...], default: "1.0.0" } } }
      const rawMachineVersions = data.machineVersions || {}
      const machineVers: Record<string, string[]> = {}
      const defaultVers: Record<string, string> = {}
      const selectedVers: Record<string, string> = {}

      for (const [machineName, info] of Object.entries(rawMachineVersions)) {
        const machineInfo = info as { versions: string[], default: string }
        machineVers[machineName] = machineInfo.versions || []
        defaultVers[machineName] = machineInfo.default || (machineInfo.versions?.[0] || "1.0.0")
        selectedVers[machineName] = machineInfo.default || (machineInfo.versions?.[0] || "1.0.0")
      }

      // Extract DC versions (use first DC's versions as the unified DC version list)
      const dcMachines = Object.keys(machineVers).filter(name => isDomainController(name))
      if (dcMachines.length > 0) {
        const firstDC = dcMachines[0]
        setDCVersions(machineVers[firstDC] || [])
        setUnifiedDCVersion(defaultVers[firstDC] || "1.0.0")
      }

      setMachineVersions(machineVers)
      setDefaultMachineVersions(defaultVers)
      setSelectedMachineVersions(selectedVers)

    } catch (error) {
      console.error("Error fetching versions:", error)
      setAvailableVersions([])
      setSelectedVersion("")
      setMachineVersions({})
      setSelectedMachineVersions({})
      setDefaultMachineVersions({})
    } finally {
      setIsLoadingVersions(false)
    }
  }

  // Helper function to check if a machine is a domain controller
  const isDomainController = (machineName: string): boolean => {
    // Domain controllers typically follow naming patterns: DC01, DC02, DC-*, etc.
    return /^DC\d+$|^DC-/.test(machineName.toUpperCase())
  }

  const updateMachineVersion = (machineName: string, version: string) => {
    setSelectedMachineVersions(prev => ({
      ...prev,
      [machineName]: version
    }))
  }

  const refreshScenarios = async () => {
    try {
      // Don't delete the deploymentID cookie just for refreshing scenarios
      // The user might want to stay connected to their current environment

      const scenData = await getScenarios();

      // Always use valid data
      if (Array.isArray(scenData) && scenData.length > 0) {
        setScenarioData(scenData)
        // Use updateInfoPanel to handle both state update AND version fetching
        updateInfoPanel(scenData[0])
      } else {
        setScenarioData([])
        setValue("")
        setSelected("")
      }
    } catch (error) {
      console.error("Error in refresh scenarios:", error)
      setScenarioData([])
      setValue("")
      setSelected("")
    }
  }

  const handleDeleteClick = () => {
    setIsDeleteModalOpen(true)
  }

  const handleDeleteConfirm = async () => {
    const scenarioToDelete = selected
    setIsDeleting(true)
    setIsDeleteModalOpen(false) // Close modal immediately to show loading state

    try {
      const response = await fetch(GlobalConfigs.deleteScenarioEndpoint, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ scenario: scenarioToDelete }),
      })

      if (!response.ok) {
        throw new Error(`Failed to delete scenario: ${response.statusText}`)
      }

      const result = await response.json()

      // Refresh the scenarios list
      await refreshScenarios()

      alert(`Successfully deleted ${scenarioToDelete}`)
    } catch (error) {
      console.error("Error deleting scenario:", error)
      alert(`Failed to delete scenario: ${error}`)
    } finally {
      setIsDeleting(false)
    }
  }

  useEffect(() => {
    if (effectRan.current === true) {
      return
    }

    refreshScenarios()
    effectRan.current = true
  }, [])

  return (
    <form onSubmit={onSubmit} className="flex flex-col items-center pb-5">
      <h1 className="base-title-centered base-text-color mb-6">
        Deploy
      </h1>
      <div className="flex flex-col gap-4 mb-6">
        <div className="flex items-center gap-4">
          <label className="text-slate-50 font-medium min-w-[5rem]">Scenario:</label>
          <Listbox value={selected} onChange={updateInfoPanel} disabled={scenarioData.length === 0}>
            <div className="relative w-56">
              <ListboxButton className={`w-full py-2 px-3 rounded-lg border focus:outline-none transition-all duration-200 ${
                scenarioData.length === 0
                  ? "bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed"
                  : "bg-slate-900/50 text-white border-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              }`}>
                <span className="block truncate">{selected || (scenarioData.length === 0 ? "No scenarios available" : "Select scenario")}</span>
                <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2"></span>
              </ListboxButton>
              <Transition
                as={Fragment}
                leave="transition ease-in duration-100"
                leaveFrom="opacity-100"
                leaveTo="opacity-0"
              >
                <ListboxOptions className="absolute mt-1 max-h-60 w-full overflow-auto rounded-lg bg-slate-900 border border-slate-600 py-1 text-base shadow-xl z-10 focus:outline-none sm:text-sm">
                  {scenarioData.map((item) => (
                    <ListboxOption
                      key={item}
                      className={({ focus }) =>
                        `relative cursor-default select-none py-2 pl-10 pr-4 ${
                          focus ? "bg-blue-600 text-white" : "text-slate-50"
                        }`
                      }
                      value={item}
                    >
                      {({ selected }) => (
                        <>
                          <span
                            className={`block truncate ${
                              selected ? "font-medium" : "font-normal"
                            }`}
                          >
                            {item}
                          </span>
                          {selected ? (
                            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-300"></span>
                          ) : null}
                        </>
                      )}
                    </ListboxOption>
                  ))}
                </ListboxOptions>
              </Transition>
            </div>
          </Listbox>
        </div>
        {/* Version selector - show for Build scenarios */}
        {selected.startsWith("Build-") && (
          <>
            {/* Toggle between unified and per-machine versions */}
            <div className="flex items-center gap-4">
              <label className="text-slate-50 font-medium min-w-[5rem] text-sm">Version Mode:</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setUsePerMachineVersions(false)}
                  className={`px-3 py-1 rounded-lg text-sm transition-all duration-200 ${
                    !usePerMachineVersions
                      ? "bg-blue-600 text-white border border-blue-500"
                      : "bg-slate-800 text-slate-400 border border-slate-600 hover:bg-slate-700"
                  }`}
                >
                  Unified
                </button>
                <button
                  type="button"
                  onClick={() => setUsePerMachineVersions(true)}
                  className={`px-3 py-1 rounded-lg text-sm transition-all duration-200 ${
                    usePerMachineVersions
                      ? "bg-blue-600 text-white border border-blue-500"
                      : "bg-slate-800 text-slate-400 border border-slate-600 hover:bg-slate-700"
                  }`}
                >
                  Per-Machine
                </button>
              </div>
            </div>

            {/* Unified version selector */}
            {!usePerMachineVersions && (
              <div className="flex items-center gap-4">
                <label className="text-slate-50 font-medium min-w-[5rem]">Version:</label>
                <Listbox value={selectedVersion} onChange={setSelectedVersion}>
                  <div className="relative w-56">
                    <ListboxButton className="w-full bg-slate-900/50 text-white py-2 px-3 rounded-lg border border-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition-all duration-200">
                      <span className="block truncate">
                        {isLoadingVersions ? "Loading..." : selectedVersion || "Select version"}
                      </span>
                      <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2"></span>
                    </ListboxButton>
                    <Transition
                      as={Fragment}
                      leave="transition ease-in duration-100"
                      leaveFrom="opacity-100"
                      leaveTo="opacity-0"
                    >
                      <ListboxOptions className="absolute mt-1 max-h-60 w-full overflow-auto rounded-lg bg-slate-900 border border-slate-600 py-1 text-base shadow-xl z-10 focus:outline-none sm:text-sm">
                        {availableVersions.map((version) => (
                          <ListboxOption
                            key={version}
                            className={({ focus }) =>
                              `relative cursor-default select-none py-2 pl-10 pr-4 ${
                                focus ? "bg-blue-600 text-white" : "text-slate-50"
                              }`
                            }
                            value={version}
                          >
                            {({ selected }) => (
                              <>
                                <span
                                  className={`block truncate ${
                                    selected ? "font-medium" : "font-normal"
                                  }`}
                                >
                                  {version}
                                </span>
                                {selected ? (
                                  <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-300"></span>
                                ) : null}
                              </>
                            )}
                          </ListboxOption>
                        ))}
                      </ListboxOptions>
                    </Transition>
                  </div>
                </Listbox>
              </div>
            )}

            {/* Per-machine version selectors */}
            {usePerMachineVersions && Object.keys(machineVersions).length > 0 && (
              <div className="w-full max-w-md">
                <label className="text-slate-50 font-medium block mb-3">Machine Versions:</label>
                <div className="space-y-3">
                  {/* Unified Domain Controller Version Selector */}
                  {dcVersions.length > 0 && (
                    <div className="bg-slate-800/70 rounded-lg p-3 border border-blue-600/50">
                      <div className="text-slate-300 text-xs mb-2 italic">
                        All Domain Controllers will use the same version to maintain consistent user/attack configuration.
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-blue-400 font-semibold text-sm w-32">
                          Domain Controllers:
                        </span>
                        <Listbox
                          value={unifiedDCVersion}
                          onChange={(v) => setUnifiedDCVersion(v)}
                        >
                          <div className="relative flex-1">
                            <ListboxButton className="w-full bg-slate-900/50 text-white py-1.5 px-3 rounded-lg border border-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition-all duration-200 text-sm font-medium">
                              <span className="block truncate">
                                {unifiedDCVersion || "Select"}
                              </span>
                            </ListboxButton>
                            <Transition
                              as={Fragment}
                              leave="transition ease-in duration-100"
                              leaveFrom="opacity-100"
                              leaveTo="opacity-0"
                            >
                              <ListboxOptions className="absolute mt-1 max-h-40 w-full overflow-auto rounded-lg bg-slate-900 border border-slate-600 py-1 text-sm shadow-xl z-20 focus:outline-none">
                                {dcVersions.map((version) => (
                                  <ListboxOption
                                    key={version}
                                    className={({ focus }) =>
                                      `relative cursor-default select-none py-1.5 px-3 ${
                                        focus ? "bg-blue-600 text-white" : "text-slate-50"
                                      }`
                                    }
                                    value={version}
                                  >
                                    {({ selected }) => (
                                      <span className={`block truncate ${selected ? "font-medium" : "font-normal"}`}>
                                        {version}
                                      </span>
                                    )}
                                  </ListboxOption>
                                ))}
                              </ListboxOptions>
                            </Transition>
                          </div>
                        </Listbox>
                      </div>
                    </div>
                  )}

                  {/* Other Machines */}
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-600 max-h-60 overflow-y-auto space-y-2">
                    {Object.entries(machineVersions)
                      .filter(([machineName]) => !isDomainController(machineName))
                      .map(([machineName, versions]) => (
                    <div key={machineName} className="flex items-center gap-3">
                      <span className="text-slate-300 font-mono text-sm w-32 truncate" title={machineName}>
                        {machineName}:
                      </span>
                      <Listbox
                        value={selectedMachineVersions[machineName] || ""}
                        onChange={(v) => updateMachineVersion(machineName, v)}
                      >
                        <div className="relative flex-1">
                          <ListboxButton className="w-full bg-slate-900/50 text-white py-1 px-2 rounded-lg border border-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition-all duration-200 text-sm">
                            <span className="block truncate">
                              {selectedMachineVersions[machineName] || "Select"}
                            </span>
                          </ListboxButton>
                          <Transition
                            as={Fragment}
                            leave="transition ease-in duration-100"
                            leaveFrom="opacity-100"
                            leaveTo="opacity-0"
                          >
                            <ListboxOptions className="absolute mt-1 max-h-40 w-full overflow-auto rounded-lg bg-slate-900 border border-slate-600 py-1 text-sm shadow-xl z-20 focus:outline-none">
                              {versions.map((version) => (
                                <ListboxOption
                                  key={version}
                                  className={({ focus }) =>
                                    `relative cursor-default select-none py-1 px-2 ${
                                      focus ? "bg-blue-600 text-white" : "text-slate-50"
                                    }`
                                  }
                                  value={version}
                                >
                                  {({ selected }) => (
                                    <span className={`block truncate ${selected ? "font-medium" : "font-normal"}`}>
                                      {version}
                                    </span>
                                  )}
                                </ListboxOption>
                              ))}
                            </ListboxOptions>
                          </Transition>
                        </div>
                      </Listbox>
                    </div>
                  ))}
                </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="flex flex-col gap-3 mt-6">
        <button
          type="submit"
          className={
            isButtonDisabled || !selected
              ? "btn-primary opacity-50 cursor-not-allowed w-48"
              : "btn-primary w-48"
          }
          disabled={isButtonDisabled || !selected}
        >
          {isButtonDisabled ? "Please Wait" : "Submit"}
        </button>
        <button
          type="button"
          onClick={refreshScenarios}
          className="btn-secondary w-48"
        >
          Refresh Scenarios
        </button>
        {selected.startsWith("Build-") && (
          <button
            type="button"
            onClick={handleDeleteClick}
            disabled={isDeleting}
            className={
              isDeleting
                ? "btn-danger opacity-50 cursor-not-allowed w-48"
                : "btn-danger w-48"
            }
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        )}
      </div>
      <DeleteScenarioModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleDeleteConfirm}
        scenarioName={selected}
      />
    </form>
  )
}
