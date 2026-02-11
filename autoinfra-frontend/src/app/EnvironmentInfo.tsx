import React, { useState, useEffect } from "react"
import { DeleteCookie, GetCookie } from "@/components/cookieHandler"
import PasswordDisplay from "@/components/passwordDisplay"
import Timer from "@/components/timer"
import Loading from "@/components/loading"
import GlobalConfigs from "./app.config"
import { useDeployments } from "@/contexts/DeploymentContext"
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Description,
} from "@headlessui/react"

// Save blocker duration (10 minutes)
const SAVE_BLOCKER_DURATION = 10 * 60 * 1000

export default function EnvironmentInfo() {
  const [deployID, setDeployID] = useState("")
  const [scenario, setScenario] = useState("")
  const [scenarioSubType, setScenarioSubType] = useState("")
  const [entryIP, setEntryIP] = useState("")
  const [entryIPs, setEntryIPs] = useState<Record<string, string>>({})
  const [port, setPort] = useState("")
  const [deploymentID, setDeploymentID] = useState("")
  const [isButtonDisabled, setButtonDisabled] = useState(true)
  const [jumpboxUser, setJumpboxUser] = useState("")
  const [jumpboxPassword, setJumpboxPassword] = useState("")
  const [enterpriseAdminUser, setEnterpriseAdminUser] = useState("")
  const [enterpriseAdminPassword, setEnterpriseAdminPassword] = useState("")
  const [hasJumpbox, setHasJumpbox] = useState(false)
  const [scenarioInfo, setScenarioInfo] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [isMounted, setIsMounted] = useState(false)
  const [isSavingScenario, setIsSavingScenario] = useState(false)
  const [scenarioExists, setScenarioExists] = useState(false)
  const [isUpdatingScenario, setIsUpdatingScenario] = useState(false)

  // Save blocker - 10 minute timer after deployment
  const [deploymentStartTime, setDeploymentStartTime] = useState<number | null>(null)
  const [saveBlockerRemaining, setSaveBlockerRemaining] = useState<number>(0)

  // Local state override for manual actions (shutdown/save)
  const [localStateOverride, setLocalStateOverride] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Get deployment state from context, with local override
  const { getDeploymentState, refreshDeployments } = useDeployments()
  const contextState = deploymentID ? getDeploymentState(deploymentID) : null
  // If we have a deploymentID but no context state, assume it's deploying (handles new builds)
  const defaultState = (deploymentID && deploymentID !== "error" && deploymentID !== "false" && !contextState) ? "deploying" : contextState
  const envState = localStateOverride || defaultState

  // Check if save is blocked
  const isSaveBlocked = saveBlockerRemaining > 0

  // Format time remaining
  const formatTimeRemaining = (ms: number): string => {
    const minutes = Math.floor(ms / 60000)
    const seconds = Math.floor((ms % 60000) / 1000)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  // Load deploymentID from cookie on client side only to avoid hydration errors
  useEffect(() => {
    setIsMounted(true)
    const cookieValue = GetCookie("deploymentID")
    if (cookieValue && cookieValue !== "error" && cookieValue !== "false") {
      setDeploymentID(cookieValue)
    }
  }, [])

  // Initialize save blocker when deployment COMPLETES (for Build deployments)
  // Timer starts when entry IP is shown to user, not when deployment starts
  useEffect(() => {
    if (deploymentID && deploymentID.startsWith("BuildLab-") && envState === "deployed" && !deploymentStartTime) {
      // Check for stored start time, or create new one when deployment completes
      const storedStartTime = localStorage.getItem(`saveBlocker_${deploymentID}`)
      if (storedStartTime) {
        setDeploymentStartTime(parseInt(storedStartTime, 10))
      } else {
        // Deployment just completed - start the timer now
        const now = Date.now()
        localStorage.setItem(`saveBlocker_${deploymentID}`, now.toString())
        setDeploymentStartTime(now)
      }
    }
  }, [deploymentID, envState, deploymentStartTime])

  // Save blocker countdown timer
  useEffect(() => {
    if (!deploymentStartTime) {
      setSaveBlockerRemaining(0)
      return
    }

    const updateRemaining = () => {
      const elapsed = Date.now() - deploymentStartTime
      const remaining = Math.max(0, SAVE_BLOCKER_DURATION - elapsed)
      setSaveBlockerRemaining(remaining)

      // Clean up localStorage when timer expires
      if (remaining === 0 && deploymentID) {
        localStorage.removeItem(`saveBlocker_${deploymentID}`)
      }
    }

    updateRemaining()
    const interval = setInterval(updateRemaining, 1000)
    return () => clearInterval(interval)
  }, [deploymentStartTime, deploymentID])

  const getInfo = async () => {
    const response = await fetch(GlobalConfigs.getDeploymentInfoEndpoint, {
      method: "POST",
      body: deploymentID,
    })
    return await response.json()
  }

  const getScenarioInfo = async (scenario: string) => {
    const response = await fetch(GlobalConfigs.getScenarioInfoEndpoint, {
      method: "POST",
      body: scenario,
    })
    return await response.json()
  }

  const getJumpboxCreds = async () => {
    const response = await fetch(GlobalConfigs.getJumpboxCredsEndpoint, {
      method: "GET",
    })
    return await response.json()
  }

  const getTopology = async (deploymentID: string, scenarioName: string) => {
    const response = await fetch(GlobalConfigs.getTopologyEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deploymentID, scenarioName }),
    })
    return await response.json()
  }

  // Consolidated function to update deployment info based on state
  const updateDeploymentInfo = (state: string, data: any) => {
    if (state === "deploying") {
      setEntryIP("Deploying")
      setEntryIPs({})
      setPort("")
      setButtonDisabled(true)
    } else if (state === "deployed") {
      setEntryIP(data.message.entryIP)
      setEntryIPs(data.message.entryIPs || {})
      setPort(data.message.dockerfilePort)
      setButtonDisabled(false)
    }
  }

  // Refetch deployment data (without state - that comes from context)
  const refetchDeploymentInfo = async () => {
    try {
      const data = await getInfo()
      const state = deploymentID ? getDeploymentState(deploymentID) : null
      if (state) {
        updateDeploymentInfo(state, data)
      }
    } catch (error) {
      console.error("Error refetching deployment info:", error)
    }
  }

  // Trigger refresh if we have a deploymentID but no state from context
  useEffect(() => {
    const handleMissingState = async () => {
      if (
        deploymentID &&
        deploymentID !== "error" &&
        deploymentID !== "false" &&
        !envState &&
        !isRefreshing
      ) {
        setIsRefreshing(true)
        await refreshDeployments()
        setIsRefreshing(false)
      }
    }
    handleMissingState()
  }, [deploymentID, envState, isRefreshing, refreshDeployments])

  useEffect(() => {
    // Clear local state override when deployment changes
    setLocalStateOverride(null)
    // Reset scenarioExists to default when deployment changes
    setScenarioExists(false)

    const getInfoEffect = async () => {
      if (
        deploymentID &&
        deploymentID !== "error" &&
        deploymentID !== "false"
      ) {
        const data = await getInfo()
        const state = getDeploymentState(deploymentID)
        try {
          setDeployID(deploymentID)

          // Check if this is a scenario or custom topology
          if (data.message.scenario && data.message.scenario !== "Custom Topology") {
            // This is a deployed scenario (not a build)
            setScenario(data.message.scenario)
            const scenData = await getScenarioInfo(data.message.scenario)
            setScenarioSubType(scenData.message.subtype)
            // Deployed scenarios always have the scenario already
            setScenarioExists(true)
          } else if (data.message.topology || data.message.scenario === "Custom Topology") {
            // This is a custom build
            setScenario("Custom Topology")
            setScenarioSubType("NETWORK")
            // Get scenario description from deployment for custom builds
            if (data.message.scenarioInfo) {
              setScenarioInfo(data.message.scenarioInfo)
            }

            // Check if this build has been saved as a scenario already
            if (deploymentID.startsWith("BuildLab-")) {
              const parts = deploymentID.split("-")
              const scenarioName = `Build-${parts[parts.length - 1]}`
              try {
                const scenarioCheckResponse = await fetch(
                  GlobalConfigs.getScenarioInfoEndpoint,
                  {
                    method: "POST",
                    body: scenarioName,
                  }
                )
                const scenarioCheckData = await scenarioCheckResponse.json()
                // Scenario exists ONLY if:
                // 1. Response was OK (not 404)
                // 2. message is an object (not a string like "Scenario not found.")
                const exists =
                  scenarioCheckResponse.ok &&
                  scenarioCheckData?.message &&
                  typeof scenarioCheckData.message === 'object'

                setScenarioExists(exists)
              } catch (error) {
                console.error("Error checking if scenario exists:", error)
                setScenarioExists(false)
              }
            }
          }

          // Fetch topology to get enterprise admin creds and check for jumpbox
          try {
            const topologyData = await getTopology(deploymentID, data.message.scenario)
            if (topologyData.topology) {
              const topology = topologyData.topology
              // Get enterprise admin credentials
              if (topology.credentials) {
                setEnterpriseAdminUser(topology.credentials.enterpriseAdminUsername || "")
                setEnterpriseAdminPassword(topology.credentials.enterpriseAdminPassword || "")
              }
              // Check if jumpbox exists in nodes
              const nodes = topology.nodes || []
              const jumpboxExists = nodes.some((node: any) => node.type === "jumpbox")
              setHasJumpbox(jumpboxExists)
            }
          } catch (error) {
            console.error("Error fetching topology:", error)
          }

          // Only fetch jumpbox creds if there's a jumpbox (for NETWORK scenarios)
          const jumpboxCreds = await getJumpboxCreds()
          if (jumpboxCreds.message && jumpboxCreds.message.includes(":")) {
            const [user, pass] = jumpboxCreds.message.split(":")
            setJumpboxUser(user)
            setJumpboxPassword(pass)
          }

          // Set deployment info based on state
          if (state) {
            updateDeploymentInfo(state, data)
          }
        } catch (error) {
          console.error("Error:", error)
          // Only delete cookie if the deployment is truly not found or invalid
          // Don't delete on temporary network errors
        }
      } else {
        setDeployID("No Environment")
        setButtonDisabled(true)
        setLocalStateOverride("noDeployment")
      }
    }
    getInfoEffect()
  }, [deploymentID])

  // Update deployment info when envState changes (fixes refresh issue)
  useEffect(() => {
    const updateInfoOnStateChange = async () => {
      if (
        envState &&
        envState !== "noDeployment" &&
        deploymentID &&
        deploymentID !== "error" &&
        deploymentID !== "false"
      ) {
        try {
          const data = await getInfo()
          updateDeploymentInfo(envState, data)
        } catch (error) {
          console.error("Error updating deployment info on state change:", error)
        }
      }
    }
    updateInfoOnStateChange()
  }, [envState, deploymentID])

  const handleShutdownClick = () => {
    // Immediately set state to trigger UI update
    setButtonDisabled(true)
    setLocalStateOverride("noDeployment")
    setDeployID("No Environment")
    setEntryIP("")
    setEntryIPs({})
    setScenario("")
    setPort("")
    setDeploymentID("")
    setEnterpriseAdminUser("")
    setEnterpriseAdminPassword("")
    setJumpboxUser("")
    setJumpboxPassword("")
    setHasJumpbox(false)

    // Delete cookie immediately
    DeleteCookie("deploymentID")

    fetch(GlobalConfigs.shutdownEndpoint, {
      method: "POST",
      body: deploymentID,
    })
      .then((response) => response.json())
      .then(() => {
        // Wait a moment before refreshing to ensure backend has processed the shutdown
        setTimeout(() => {
          refreshDeployments()
        }, 2000)
      })
      .catch((error) => {
        console.error("Error shutting down:", error)
        // On error, restore the deployment state
        setLocalStateOverride(null)
      })
  }

  const handleExtendClick = () => {
    fetch(GlobalConfigs.extendTimeEndpoint, {
      method: "POST",
      body: deploymentID,
    })
      .then((response) => response.json())
      .then((data) => {
        fetch(GlobalConfigs.getDeploymentTimeoutEndpoint, {
          method: "POST",
          body: deploymentID,
        })
          .then((response) => response.json())
          .then((data) => {
            setEndTimeout(data.message)
          })
          .catch((error) => {
            console.error("Error fetching updated timeout:", error)
          })
      })
      .catch((error) => {
        console.error("Error extending time:", error)
      })
  }

  const handleSaveDeployment = () => {
    fetch(GlobalConfigs.saveDeploymentEndpoint, {
      method: "POST",
      body: deploymentID,
    })
      .then((response) => response.json())
      .then((data) => {

        // Trigger immediate refresh of deployments context
        refreshDeployments()

        // Only delete cookie after successful save
        DeleteCookie("deploymentID")

        // Update state to show no environment after saving
        setLocalStateOverride("noDeployment")
        setDeployID("No Environment")
        setEntryIP("")
        setEntryIPs({})
        setScenario("")
        setPort("")
        setDeploymentID("")
        setEnterpriseAdminUser("")
        setEnterpriseAdminPassword("")
        setJumpboxUser("")
        setJumpboxPassword("")
        setHasJumpbox(false)
        setButtonDisabled(true)
        setIsOpen(false)
      })
      .catch((error) => {
        console.error("Error saving deployment:", error)
      })
  }

  const handleInitialSaveClick = () => {
    fetch(GlobalConfigs.getSavedDeploymentInfoEndpoint, {
      method: "POST",
      body: deploymentID,
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.message === false) {
          handleSaveDeployment()
        } else {
          setIsOpen(true)
        }
      })
  }

  const handleSaveAsScenarioClick = () => {
    setIsSavingScenario(true)
    fetch(GlobalConfigs.createBuildScenarioEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ deploymentId: deploymentID }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.scenarioName) {
          alert(`Successfully created scenario: ${data.scenarioName}`)
          setScenarioExists(true) // Mark that scenario now exists
        } else {
          alert("Error creating scenario")
        }
      })
      .catch((error) => {
        console.error("Error saving build as scenario:", error)
        alert("Error saving build as scenario")
      })
      .finally(() => {
        setIsSavingScenario(false)
      })
  }

  const handleUpdateScenarioClick = () => {
    setIsUpdatingScenario(true)
    fetch(GlobalConfigs.updateScenarioEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ deploymentId: deploymentID }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.scenarioName) {
          alert(`Successfully updated scenario: ${data.scenarioName} to version ${data.newVersion}`)
        } else {
          alert("Error updating scenario")
        }
      })
      .catch((error) => {
        console.error("Error updating scenario:", error)
        alert("Error updating scenario")
      })
      .finally(() => {
        setIsUpdatingScenario(false)
      })
  }

  const [endTimeout, setEndTimeout] = useState(0)

  // Fetch timeout info in useEffect (moved from render)
  useEffect(() => {
    if (deploymentID && deploymentID !== "error" && deploymentID !== "false") {
      fetch(GlobalConfigs.getDeploymentTimeoutEndpoint, {
        method: "POST",
        body: deploymentID,
      })
        .then((response) => response.json())
        .then((data) => {
          setEndTimeout(data.message)
        })
        .catch((error) => {
          console.error("Error fetching timeout:", error)
        })
    } else {
      // Reset timeout when there's no deployment
      setEndTimeout(0)
    }
  }, [deploymentID])

  // Watch for deployment state changes from context and handle IP updates
  useEffect(() => {
    // Handle build deployment completion - trigger IP update
    if (
      envState === "deployed" &&
      deploymentID &&
      deploymentID.startsWith("BuildLab-")
    ) {

      // Only trigger IP update if we don't have an entry IP yet
      if (!entryIP || entryIP === "Deploying") {
        fetch(GlobalConfigs.updateBuildIPEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ deploymentID }),
        })
          .then((response) => {
            if (response.ok) {
              // Refetch deployment info after a short delay to get updated IP
              setTimeout(() => refetchDeploymentInfo(), 3000)
            } else {
              console.error("Failed to trigger IP update")
            }
          })
          .catch((error) => {
            console.error("Error triggering IP update:", error)
          })
      }
    }
  }, [envState, deploymentID, entryIP])

  // Show loading during SSR and initial mount to prevent hydration errors
  if (!isMounted) {
    return <Loading />
  }

  // Show loading only if we truly don't know the state
  if (envState === null || envState === undefined) {
    return <Loading />
  }

  if (envState === "deploying" || envState === "deployed") {
    return (
      <>
        <h1 className="heading-lg">Current Environment</h1>
        <br></br>
        <div className="current-environment-info-container">
          Deployment ID:{" "}
          <span className="current-environment-info-display">{deployID}</span>
          <br></br>
          Scenario:{" "}
          <span className="current-environment-info-display">{scenario}</span>
          <br></br>
          {/* Display entry IPs with node names */}
          {Object.keys(entryIPs).length > 0 ? (
            Object.entries(entryIPs).map(([nodeName, ip]) => (
              <div key={nodeName}>
                {nodeName} Entry IP:{" "}
                <span className="current-environment-info-display">
                  {ip}
                  {port !== "" && <>:{port}</>}
                </span>
              </div>
            ))
          ) : (
            <>
              Entry IP:{" "}
              <span className="current-environment-info-display">
                {entryIP}
                {port !== "" && <>:{port}</>}
              </span>
              <br></br>
            </>
          )}
          <div className="flex">
            Timeout:
            <div className="pl-3 current-environment-info-display">
              {envState === "deployed" ? (
                endTimeout > 0 ? (
                  <Timer
                    timeout={endTimeout}
                    onTimerExpired={handleShutdownClick}
                  />
                ) : (
                  "Loading..."
                )
              ) : (
                "Deploying"
              )}
            </div>
          </div>
        </div>
        <div className="pt-5">
          <button
            onClick={handleExtendClick}
            className={isButtonDisabled ? "" : "base-button"}
          >
            {isButtonDisabled ? "" : "Extend"}
          </button>

          {/* For builds: Show "Save as Scenario" initially, then "Save" (update) after scenario created */}
          {scenario === "Custom Topology" && !isButtonDisabled && !scenarioExists && (
            <button
              onClick={handleSaveAsScenarioClick}
              className={(isSavingScenario || isSaveBlocked) ? "base-button opacity-50 cursor-not-allowed" : "base-button"}
              disabled={isSavingScenario || isSaveBlocked}
              title={isSaveBlocked ? `Wait ${formatTimeRemaining(saveBlockerRemaining)} before saving (allows AD sync to complete)` : isSavingScenario ? "Creating snapshots... This may take 10-15 minutes" : ""}
            >
              {isSavingScenario ? (
                <span className="flex items-center gap-2">
                  <svg
                    className="animate-spin h-4 w-4"
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
                  Creating Snapshots...
                </span>
              ) : isSaveBlocked ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Save ({formatTimeRemaining(saveBlockerRemaining)})
                </span>
              ) : (
                "Save As Scenario"
              )}
            </button>
          )}

          {/* For builds after SAS, or deployed scenarios: Show "Save" (update) button */}
          {!isButtonDisabled && scenarioExists && (scenario === "Custom Topology" || (scenario && scenario !== "No Environment")) && (
            <button
              onClick={handleUpdateScenarioClick}
              className={(isUpdatingScenario || isSaveBlocked) ? "base-button opacity-50 cursor-not-allowed" : "base-button"}
              disabled={isUpdatingScenario || isSaveBlocked}
              title={isSaveBlocked ? `Wait ${formatTimeRemaining(saveBlockerRemaining)} before saving (allows AD sync to complete)` : isUpdatingScenario ? "Creating new snapshots... This may take 10-15 minutes" : "Update scenario with current VM state"}
            >
              {isUpdatingScenario ? (
                <span className="flex items-center gap-2">
                  <svg
                    className="animate-spin h-4 w-4"
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
                  Updating...
                </span>
              ) : isSaveBlocked ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Save ({formatTimeRemaining(saveBlockerRemaining)})
                </span>
              ) : (
                "Save"
              )}
            </button>
          )}

          <button
            onClick={handleShutdownClick}
            className={isButtonDisabled ? "" : "base-button"}
          >
            {isButtonDisabled ? "" : "Shut Down"}
          </button>
        </div>
        {scenarioSubType === "NETWORK" && (
          <>
            {/* Enterprise Admin Credentials - Always shown */}
            <div className="current-environment-info-container pt-5">
              Enterprise Admin Credentials:
              <div className="password-display pt-5">
                <div className="password-row">
                  <span>Username: </span>
                  <span className="current-environment-info-display">
                    {enterpriseAdminUser || "Loading..."}
                  </span>
                </div>
                <div className="password-row">
                  <span>Password: </span>
                  <span className="current-environment-info-display">
                    <PasswordDisplay password={enterpriseAdminPassword} />
                  </span>
                </div>
              </div>
            </div>

            {/* Jumpbox Credentials - Only shown if jumpbox exists */}
            {hasJumpbox && jumpboxUser && (
              <div className="current-environment-info-container pt-5">
                Jumpbox Credentials:
                <div className="password-display pt-5">
                  <div className="password-row">
                    <span>Username: </span>
                    <span className="current-environment-info-display">
                      {jumpboxUser}
                    </span>
                  </div>
                  <div className="password-row">
                    <span>Password: </span>
                    <span className="current-environment-info-display">
                      <PasswordDisplay password={jumpboxPassword} />
                    </span>
                  </div>
                </div>
              </div>
            )}
            <Dialog open={isOpen} onClose={() => setIsOpen(false)} className="">
              <div className="dialog-overlay">
                <DialogPanel className="dialog-panel">
                  <DialogTitle className="dialog-title">
                    Warning! Previous Save Detected!
                  </DialogTitle>
                  <Description className="dialog-description">
                    This will overwrite the previous save file for this
                    deployment.
                  </Description>
                  <p className="text-center">Proceed?</p>
                  <div className="dialog-button-group">
                    <button
                      onClick={() => setIsOpen(false)}
                      className="dialog-button"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveDeployment}
                      className="dialog-button"
                    >
                      Yes
                    </button>
                  </div>
                </DialogPanel>
              </div>
            </Dialog>
          </>
        )}
      </>
    )
  } else {
    return (
      <>
        <h1 className="heading-lg">Current Environment</h1>
        <br></br>
        <div className="current-environment-info-display">No Environment</div>
      </>
    )
  }
}
