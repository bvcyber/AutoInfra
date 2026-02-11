"use client"
import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from "react"
import GlobalConfigs from "../app/app.config"

// Types
interface Deployment {
  id: string
  scenario: string
  state: string
  vmName?: string
  vmSize?: string
  region?: string
  type?: string
  publicIP?: string
  fqdn?: string
  adminUsername?: string
}

interface DeploymentContextType {
  deployments: Deployment[]
  isLoading: boolean
  getDeploymentState: (deploymentId: string) => string | undefined
  refreshDeployments: () => Promise<void>
}

// Create context
const DeploymentContext = createContext<DeploymentContextType | undefined>(undefined)

// Provider component
export function DeploymentProvider({ children }: { children: ReactNode }) {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const isPollingRef = useRef(false)
  const pollCounterRef = useRef(0)

  // Fetch list of deployments
  const getDeployedEnvironments = async () => {
    try {
      const response = await fetch(GlobalConfigs.listDeploymentsEndpoint)
      const data = await response.json()
      return data
    } catch (error) {
      console.error("Error fetching environments:", error)
      return { message: {} }
    }
  }

  // Fetch state for a single deployment
  const getEnvironmentState = async (deploymentID: string) => {
    try {
      const stateResponse = await fetch(
        GlobalConfigs.getDeploymentStateEndpoint,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ deploymentID }),
        }
      )

      if (stateResponse.ok) {
        const stateData = await stateResponse.json()
        return stateData.message || "unknown"
      }
      return "unknown"
    } catch (error) {
      console.error(`Error fetching state for ${deploymentID}:`, error)
      return "unknown"
    }
  }

  // Main polling function
  const fetchAndUpdateDeployments = async () => {
    // Skip if already polling
    if (isPollingRef.current) {
      return
    }

    try {
      isPollingRef.current = true
      pollCounterRef.current++
      const data = await getDeployedEnvironments()

      if (data.message) {
        // Capture current deployments list
        let currentList: Deployment[] = []
        setDeployments((list) => {
          currentList = list
          return list
        })

        // Fetch states selectively based on current state
        const updatePromises = Object.entries(data.message).map(
          async ([_, deployment]: [string, any]) => {
            const existingDeployment = currentList.find(
              (dep) => dep.id === deployment.deploymentID
            )

            let state: string

            // Only poll Azure for state every 4 cycles (60 seconds) if already deployed
            const shouldSkipPoll =
              existingDeployment &&
              existingDeployment.state === "deployed" &&
              pollCounterRef.current % 4 !== 0

            if (shouldSkipPoll) {
              // Keep existing state for stable deployments
              state = existingDeployment.state
            } else {
              // Fetch state for new, active, or periodic check of deployed environments
              state = await getEnvironmentState(deployment.deploymentID)
            }

            return {
              id: deployment.deploymentID,
              scenario: deployment.scenario,
              state: state,
            }
          }
        )

        // Wait for all state checks and update list once
        const deploymentsWithState = await Promise.all(updatePromises)
        setDeployments(deploymentsWithState)

        // Log active environments for debugging
        const activeCount = deploymentsWithState.filter(
          (dep) =>
            dep.state === "deploying" ||
            dep.state === "saving" ||
            dep.state === "shutting down"
        ).length

        if (activeCount > 0) {
        }
      }
    } catch (error) {
      console.error("[DeploymentContext] Error polling deployments:", error)
    } finally {
      isPollingRef.current = false
    }
  }

  // Initial load
  useEffect(() => {
    const initialLoad = async () => {
      setIsLoading(true)
      await fetchAndUpdateDeployments()
      setIsLoading(false)
    }

    initialLoad()
  }, [])

  // Polling effect
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null

    // Start polling after component mounts (after initial load)
    // Delay start to avoid collision with initial load
    setTimeout(() => {
      // Poll every 30 seconds, but only check Azure state for stable deployments every 2 minutes
      interval = setInterval(fetchAndUpdateDeployments, 30000)
    }, 20000)

    // Also poll when page becomes visible (user switches back to tab or navigates to this page)
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        pollCounterRef.current = 0 // Reset counter to force full poll
        fetchAndUpdateDeployments()
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)

    // Cleanup
    return () => {
      if (interval) {
        clearInterval(interval)
      }
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [])

  // Helper to get state for a specific deployment
  const getDeploymentState = (deploymentId: string) => {
    return deployments.find((dep) => dep.id === deploymentId)?.state
  }

  // Manual refresh function
  const refreshDeployments = async () => {
    // Reset poll counter to force full state check on next poll
    pollCounterRef.current = 0
    await fetchAndUpdateDeployments()
  }

  return (
    <DeploymentContext.Provider
      value={{
        deployments,
        isLoading,
        getDeploymentState,
        refreshDeployments,
      }}
    >
      {children}
    </DeploymentContext.Provider>
  )
}

// Custom hook to use the context
export function useDeployments() {
  const context = useContext(DeploymentContext)
  if (context === undefined) {
    throw new Error("useDeployments must be used within a DeploymentProvider")
  }
  return context
}
