"use client"

import React, { useState, useEffect } from "react"
import {
  Disclosure,
  DisclosureButton,
  DisclosurePanel,
  Tab,
  TabGroup,
  TabList,
  TabPanel,
  TabPanels,
} from "@headlessui/react"
import GlobalConfigs from "@/app/app.config"
import { GetCookie } from "@/components/cookieHandler"
import "@/app/styles.css"
import TopologyVisualization from "@/components/TopologyVisualization"
import Loading from "@/components/loading"
import { useDeployments } from "@/contexts/DeploymentContext"

interface AttackInfo {
  title: string
  info: string
  requiresUser?: boolean
  requiresTargetBox?: boolean
}

interface UserOperation {
  id: string
  type: "fixed-users" | "random-users" | "single-user"
  status: "running" | "succeeded" | "failed" | "idle"
  message: string
  error?: string
  timestamp: number
  details?: {
    username?: string
    domain?: string
    usersCreated?: string[]
    numberOfUsers?: number
  }
}

type Attacks = Record<string, AttackInfo>
type AttackDataState =
  | Attacks
  | "No Environment"
  | "Could not get enabled attacks"
  | "Could not load deployment"

export default function InfoAndConfig({
  incomingSelectedScenarioFromParent,
  pageLocation,
}) {
  const [deploymentID, setDeploymentID] = useState(GetCookie("deploymentID"))
  const { deployments } = useDeployments()
  const [deployed, setDeployed] = useState(false) // Reintroduce the deployed state

  // Poll cookie for changes (e.g., when deployment is shut down)
  useEffect(() => {
    const interval = setInterval(() => {
      const currentCookie = GetCookie("deploymentID")
      if (currentCookie !== deploymentID) {
        setDeploymentID(currentCookie)
      }
    }, 1000) // Check every second
    return () => clearInterval(interval)
  }, [deploymentID])
  const getInfo = async () => {
    const response = await fetch(GlobalConfigs.getDeploymentInfoEndpoint, {
      method: "POST",
      body: deploymentID,
    })
    return await response.json()
  }

  const getScenarioInfo = async (scen: string) => {
    const response = await fetch(GlobalConfigs.getScenarioInfoEndpoint, {
      method: "POST",
      body: scen,
    })
    return await response.json()
  }

  // Helper function to format user display - handles both legacy strings and new {username, domain, dc} objects
  const formatUserDisplay = (user: any): string => {
    if (!user) return ""
    if (typeof user === "string") return user
    if (typeof user === "object" && user.username) {
      // Format as "username@domain" (UPN style) if domain exists
      if (user.domain) {
        return `${user.username}@${user.domain}`
      }
      return user.username
    }
    return String(user)
  }

  const getSavedDeploymentInfo = async (saved_deployment: string) => {
    const response = await fetch(GlobalConfigs.getSavedDeploymentInfoEndpoint, {
      method: "POST",
      body: saved_deployment,
    })
    return await response.json()
  }

  const [selectedAttack, setSelectedAttack] = useState<string | null>(null)

  const [deployID, setDeployID] = useState("")
  const [scenario, setScenario] = useState("")
  const [scenarioInfo, setScenarioInfo] = useState<{
    info: string
    savedInfo?: string
  }>({ info: "" })
  const [enabledAttacks, setEnabledAttacks] =
    useState<AttackDataState>("No Environment")
  const [attacksInProgress, setAttacksInProgress] = useState<AttackDataState>(
    {}
  )
  const [applicableAttackData, setApplicableAttackdata] =
    useState<AttackDataState>("No Environment")
  const [loading, setLoading] = useState(false) // Add loading state
  const [attacksEnabling, setAttacksEnabling] = useState(false) // Track if attacks are currently being enabled
  const [singleUsername, setsingleUsername] = useState("")
  const [singleUserPasswordForUserGen, setsingleUserPasswordForUserGen] =
    useState("")
  const [targetBoxForCtf, setTargetBoxForCtf] = useState("")
  const [singleUserPassword, setsingleUserPassword] = useState<
    Record<string, string>
  >({})
  const [targetUser, setTargetUser] = useState<Record<string, string>>({})
  const [targetBox, setTargetBox] = useState<Record<string, string>>({})
  const [grantingUser, setGrantingUser] = useState<Record<string, string>>({})
  const [receivingUser, setReceivingUser] = useState<Record<string, string>>({})
  const [numberOfUsers, setnumberOfUsers] = useState("")
  const [usernameFormat, setUsernameFormat] = useState("firstname") // New state for username format
  const [difficulty, setDifficulty] = useState("")
  const [availableDomains, setAvailableDomains] = useState<
    Array<{ domainName: string; dcName: string; isRoot: boolean }>
  >([])
  const [selectedDomain, setSelectedDomain] = useState<{
    domainName: string
    dcName: string
  } | null>(null)
  // User type can be string (legacy) or object with domain info
  type UserType = string | { username: string; domain: string; dc: string }
  const [availableUsers, setAvailableUsers] = useState<UserType[]>([])
  // Helper to extract username from user (handles both string and object formats)
  const getUserName = (user: UserType): string => {
    if (typeof user === "object" && user !== null) {
      return user.username
    }
    return user
  }
  // Helper to get display name in UPN format (e.g., "User1@test.sub.build.lab")
  const getUserDisplayName = (user: UserType): string => {
    if (typeof user === "object" && user !== null) {
      return `${user.username}@${user.domain}`
    }
    return user
  }
  const [availableMachines, setAvailableMachines] = useState<
    Array<{
      machineName: string
      machineType: string
      domainName: string
      displayName: string
    }>
  >([])
  const [targetMachine, setTargetMachine] = useState<Record<string, string>>({})
  const [disclosureResetKey, setDisclosureResetKey] = useState(0)
  const [userOperations, setUserOperations] = useState<UserOperation[]>([])
  const [activeOperationId, setActiveOperationId] = useState<string | null>(
    null
  )
  const [currentlyEnablingAttack, setCurrentlyEnablingAttack] = useState(false)
  const [isSyncingUsers, setIsSyncingUsers] = useState(false)

  // Function to sync users from live AD (queries Get-ADUser on each DC)
  const syncUsersFromAD = async () => {
    if (!deploymentID) return
    
    setIsSyncingUsers(true)
    try {
      const response = await fetch(GlobalConfigs.syncUsersEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ deploymentID }),
      })
      
      const data = await response.json()
      
      if (data.users && Array.isArray(data.users)) {
        setAvailableUsers(data.users)
        alert(data.message || `Successfully synced ${data.users.length} users`)
      } else if (data.error) {
        console.error("Error syncing users:", data.error)
        alert(`Error syncing users: ${data.error}`)
      }
    } catch (error) {
      console.error("Error syncing users from AD:", error)
      alert("Failed to sync users from Active Directory")
    } finally {
      setIsSyncingUsers(false)
    }
  }

  // Function to refresh users from deployment data (cached)
  const refreshUsers = async () => {
    if (deploymentID) {
      try {
        const data = await getInfo()
        if (
          data.message !== "No active deployment" &&
          data.message !== "File not found"
        ) {
          if (data.message.users && Array.isArray(data.message.users)) {
            // Normalize users to ensure consistent format
            const normalizedUsers = data.message.users.map((u: any) => {
              if (typeof u === 'string') {
                return { username: u, domain: "root domain" }
              } else if (typeof u === 'object' && u !== null && u.username) {
                return { username: u.username, domain: u.domain || "root domain" }
              }
              return null
            }).filter((u: any) => u !== null)
            
            setAvailableUsers(normalizedUsers)
          }
        }
      } catch (error) {
        console.error("Error refreshing users:", error)
      }
    }
  }

  // Handle tab change - refresh users when switching to Attacks tab
  const handleTabChange = async (index: number) => {
    // Index 2 is the Attacks tab
    if (index === 2) {
      await refreshUsers()
    }
  }

  useEffect(() => {
    const getInfoEffect = async () => {
      // If deploymentID is empty/invalid AND we're not on Deploy/Load pages with a selected scenario, clear everything
      if (
        (!deploymentID || deploymentID === "error" || deploymentID === "false") &&
        !(pageLocation === "DEPLOY" && incomingSelectedScenarioFromParent !== "") &&
        !(pageLocation === "LOAD_DEPLOYMENT" && incomingSelectedScenarioFromParent !== "")
      ) {
        setDeployID("No Environment")
        setScenarioInfo({ info: "" })
        setApplicableAttackdata({})
        setEnabledAttacks("No Environment")
        setAvailableUsers([])
        setDeployed(false)
        setScenario("")
        return
      }

      if (incomingSelectedScenarioFromParent !== "") {
        let data: { message }
        if (pageLocation === "LOAD_DEPLOYMENT") {
          data = await getSavedDeploymentInfo(
            incomingSelectedScenarioFromParent
          )
          setScenarioInfo(data.message)
          getApplicableAttacks(data.message.scenario, "")
          getEnabledAttacks(data.message.deploymentID)
          //setEnabledAttacks(data.message.enabledAttacks)
        } else {
          data = await getScenarioInfo(incomingSelectedScenarioFromParent)
          setScenarioInfo(data.message)
          getApplicableAttacks(incomingSelectedScenarioFromParent, "")
          getEnabledAttacks(incomingSelectedScenarioFromParent)
        }
      }
      if (incomingSelectedScenarioFromParent === "" && pageLocation !== "DEPLOY") {
        const data = await getInfo()
        if (
          data.message !== "No active deployment" &&
          data.message !== "File not found"
        ) {
          try {
            setDeployID(deploymentID)

            // Check if this is a scenario or custom topology
            if (
              data.message.scenario &&
              data.message.scenario !== "Custom Topology"
            ) {
              setScenario(data.message.scenario)
              getApplicableAttacks(data.message.scenario, deploymentID)
              setScenarioInfo(
                (await getScenarioInfo(data.message.scenario)).message
              )
            } else if (data.message.topology) {
              setScenario("Custom Topology")
              // Get applicable attacks for custom topology
              getApplicableAttacks("Custom Topology", deploymentID)
              // Get description from deployment's scenarioInfo field
              let description = data.message.scenarioInfo

              // If no custom description, generate one from topology
              if (!description || description.trim() === "") {
                const topology = data.message.topology
                const components: string[] = []

                // Count domain controllers
                const rootDCs =
                  topology.nodes?.filter(
                    (n: any) => n.type === "domainController" && !n.data?.isSub
                  ).length || 0
                const subDCs =
                  topology.nodes?.filter(
                    (n: any) => n.type === "domainController" && n.data?.isSub
                  ).length || 0

                if (rootDCs > 0)
                  components.push(`${rootDCs} Root DC${rootDCs > 1 ? "s" : ""}`)
                if (subDCs > 0)
                  components.push(`${subDCs} Sub DC${subDCs > 1 ? "s" : ""}`)

                // Count CAs
                const cas =
                  topology.nodes?.filter(
                    (n: any) => n.type === "certificateAuthority"
                  ).length || 0
                if (cas > 0) components.push(`${cas} CA${cas > 1 ? "s" : ""}`)

                // Count workstations/servers (can be type "workstation" or "standalone")
                const servers =
                  topology.nodes?.filter(
                    (n: any) =>
                      n.type === "workstation" || n.type === "standalone"
                  ).length || 0
                if (servers > 0)
                  components.push(`${servers} Server${servers > 1 ? "s" : ""}`)

                // Check for jumpbox
                const hasJumpbox = topology.nodes?.some(
                  (n: any) => n.type === "jumpbox"
                )
                if (hasJumpbox) components.push("1 Jumpbox")

                description =
                  components.length > 0
                    ? components.join(", ")
                    : `${topology.nodes?.length || 0} machine${
                        (topology.nodes?.length || 0) !== 1 ? "s" : ""
                      }`
              }

              setScenarioInfo({
                info: description,
              })
            }

            // Load available users from deployment metadata
            if (data.message.users && Array.isArray(data.message.users)) {
              // Normalize users to ensure consistent format, preserving domain info if present
              const normalizedUsers = data.message.users.map((u: any) => {
                if (typeof u === 'string') {
                  return { username: u, domain: "root domain" }
                } else if (typeof u === 'object' && u !== null && u.username) {
                  return { username: u.username, domain: u.domain || "root domain" }
                }
                return null
              }).filter((u: any) => u !== null)
              setAvailableUsers(normalizedUsers)
            } else {
              setAvailableUsers([])
            }

            getEnabledAttacks(deploymentID)
            if (data.message.state === "deployed") {
              setDeployed(true) // Ensure deployed is set correctly
            }
            if (data.message.currentlyEnablingAttacks === "true") {
              setLoading(true)
            }
          } catch (error) {
            console.error("Error:", error)
          }
        } else {
          setDeployID("No Environment")
          setApplicableAttackdata({})
        }
      }
    }
    getInfoEffect()
  }, [incomingSelectedScenarioFromParent, deploymentID])

  // Watch deployment state from context and update deployed flag
  useEffect(() => {
    if (deploymentID && deploymentID !== "error" && deploymentID !== "false") {
      const deployment = deployments.find((dep) => dep.id === deploymentID)
      if (deployment) {
        if (deployment.state === "deployed" && !deployed) {
          // Deployment just finished - refresh attacks list to pick up newly tagged VMs
          setDeployed(true)
          if (scenario) {
            getApplicableAttacks(scenario, deploymentID)
          }
        } else if (deployment.state === "deploying") {
          setDeployed(false)
        }
      }
    }
  }, [deploymentID, deployments])

  const getApplicableAttacks = async (newSelection, deployID) => {
    const data = {
      scenario: newSelection,
      deploymentId: deployID,
    }
    const scenarioAttacksResponse = await fetch(
      GlobalConfigs.listAttacksEndpoint,
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    )
    const scenarioAttacksResponseData = await scenarioAttacksResponse.json()

    setApplicableAttackdata(scenarioAttacksResponseData.message)
  }

  const getEnabledAttacks = async (newSelection) => {
    const scenarioEnabledAttacksResponse = await fetch(
      GlobalConfigs.listEnabledAttacksEndpoint,
      {
        method: "POST",
        body: newSelection,
      }
    )
    const scenarioEnabledAttacks = await scenarioEnabledAttacksResponse.json()

    setEnabledAttacks(scenarioEnabledAttacks.enabled || {})
    setAttacksInProgress(scenarioEnabledAttacks.inProgress || {})
  }

  // Fetch available domains for the deployment
  const fetchAvailableDomains = async () => {
    if (!deploymentID || deploymentID === "error" || deploymentID === "false") {
      return
    }
    try {
      const response = await fetch(GlobalConfigs.getDeploymentDomainsEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ deploymentID }),
      })
      const data = await response.json()
      if (data.domains && data.domains.length > 0) {
        setAvailableDomains(data.domains)
        // Set the first domain (root) as default
        setSelectedDomain({
          domainName: data.domains[0].domainName,
          dcName: data.domains[0].dcName,
        })
      }
    } catch (error) {
      console.error("Error fetching domains:", error)
    }
  }

  // Fetch available machines for the deployment
  const fetchAvailableMachines = async () => {
    if (!deploymentID || deploymentID === "error" || deploymentID === "false") {
      return
    }
    try {
      const response = await fetch(
        GlobalConfigs.getDeploymentMachinesEndpoint,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ deploymentID }),
        }
      )
      const data = await response.json()
      if (data.machines && data.machines.length > 0) {
        setAvailableMachines(data.machines)
      }
    } catch (error) {
      console.error("Error fetching machines:", error)
    }
  }

  // Fetch domains and machines when deployment is ready
  useEffect(() => {
    if (deployed && deploymentID) {
      fetchAvailableDomains()
      fetchAvailableMachines()
    }
  }, [deployed, deploymentID])

  const [checkboxStates, setCheckboxStates] = useState({})
  useEffect(() => {
    if (typeof applicableAttackData === "object") {
      const initialState = Object.keys(applicableAttackData).reduce(
        (acc, key) => {
          acc[key] = false
          return acc
        },
        {}
      )
      setCheckboxStates(initialState)
    }
  }, [applicableAttackData])

  const handleCheckboxChange = (key) => {
    setCheckboxStates((prevState) => ({
      ...prevState,
      [key]: !prevState[key],
    }))
    setSelectedAttack(key) // Set the selected attack
  }

  const checkAttackStatus = async () => {
    try {
      const response = await fetch(GlobalConfigs.checkAttackStatusEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ deploymentId: deploymentID }),
      })
      const data = await response.json()


      // Update enabled and in-progress attacks
      if (data.enabledAttacks || data.attacksInProgress) {
        // Refresh the enabled attacks list
        getEnabledAttacks(deploymentID)
      }

      // If there are still attacks in progress, continue polling
      // attacksInProgress is now a dict grouped by attack type
      if (
        data.attacksInProgress &&
        Object.keys(data.attacksInProgress).length > 0
      ) {
        return true // Still in progress
      }

      return false // All done
    } catch (error) {
      console.error("Error checking attack status:", error)
      return false
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setAttacksEnabling(true) // Disable submit button while attacks are being enabled

    // Merge targetMachine into targetBox (targetMachine takes precedence)
    const mergedTargetBox = { ...targetBox, ...targetMachine }

    const data = {
      checkboxes: checkboxStates,
      deploymentid: deploymentID,
      attackInputs: {
        targetBox: mergedTargetBox,
        singleUserPassword,
        targetUser,
        grantingUser,
        receivingUser,
      },
    }

    try {
      const response = await fetch(GlobalConfigs.enableAttacksEndpoint, {
        method: "POST",
        body: JSON.stringify(data),
      })

      // Immediately refresh to show attacks in progress
      await getEnabledAttacks(deploymentID)

      // Clear input fields and checkboxes for next attack
      setTargetUser({})
      setTargetBox({})
      setTargetMachine({})
      setsingleUserPassword({})
      setGrantingUser({})
      setReceivingUser({})

      // Uncheck all checkboxes by setting all to false
      const clearedCheckboxes = Object.keys(checkboxStates).reduce(
        (acc, key) => {
          acc[key] = false
          return acc
        },
        {}
      )
      setCheckboxStates(clearedCheckboxes)

      // Close all disclosure panels by changing the key
      setDisclosureResetKey((prev) => prev + 1)

      // Start polling for attack status
      const pollInterval = setInterval(async () => {
        const stillInProgress = await checkAttackStatus()
        if (!stillInProgress) {
          clearInterval(pollInterval)
          setAttacksEnabling(false) // Re-enable submit button when all attacks complete
        }
      }, 5000) // Poll every 5 seconds

      // Stop polling after 10 minutes (failsafe)
      setTimeout(() => {
        clearInterval(pollInterval)
        setAttacksEnabling(false) // Re-enable submit button even if timeout reached
      }, 600000)
    } catch (error) {
      console.error("An error occurred:", error)
      setAttacksEnabling(false)
    }
  }

  const handleGenerateUsers = async (event) => {
    event.preventDefault()
    const operationId = `fixed-${Date.now()}`

    // Add operation to tracking
    const newOperation: UserOperation = {
      id: operationId,
      type: "fixed-users",
      status: "running",
      message: `Generating fixed users in ${
        selectedDomain?.domainName || "root domain"
      }`,
      timestamp: Date.now(),
      details: { domain: selectedDomain?.domainName },
    }

    setUserOperations((prev) => [...prev, newOperation])
    setActiveOperationId(operationId)

    const data = {
      deploymentID,
      targetDomain: selectedDomain?.domainName,
      targetDC: selectedDomain?.dcName,
    }

    try {
      const response = await fetch(GlobalConfigs.generateUsersEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const result = await response.json()

      // Update operation as succeeded
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "succeeded",
                message: `Successfully generated ${
                  result.users?.length || 0
                } fixed users`,
                details: { ...op.details, usersCreated: result.users },
              }
            : op
        )
      )

      // Update available users list with newly created users
      // Filter out users that already exist (handles both string and object formats)
      if (result.users && Array.isArray(result.users)) {
        const domain =
          result.domain || selectedDomain?.domainName || "root domain"
        setAvailableUsers((prev) => {
          const prevUsernames = prev.map((u) => getUserName(u))
          const newUsers = result.users
            .filter(
              (u: string) =>
                !prevUsernames.some((existing) => existing === u)
            )
            .map((u: string) => ({ username: u, domain, dc: selectedDomain?.dcName || '' }))
          return [...prev, ...newUsers]
        })
      }
    } catch (error) {
      console.error("An error occurred:", error)
      // Update operation as failed
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "failed",
                error: error instanceof Error ? error.message : String(error),
              }
            : op
        )
      )
    } finally {
      setActiveOperationId(null)
    }
  }

  const handleGenerateRandomUsers = async (event) => {
    event.preventDefault()
    const operationId = `random-${Date.now()}`
    const numUsers = parseInt(numberOfUsers, 10)

    // Add operation to tracking
    const newOperation: UserOperation = {
      id: operationId,
      type: "random-users",
      status: "running",
      message: `Generating ${numUsers} random users in ${
        selectedDomain?.domainName || "root domain"
      }`,
      timestamp: Date.now(),
      details: { domain: selectedDomain?.domainName, numberOfUsers: numUsers },
    }

    setUserOperations((prev) => [...prev, newOperation])
    setActiveOperationId(operationId)

    const data = {
      deploymentID,
      numberOfUsers: numUsers,
      usernameFormat: usernameFormat, // Add username format to request
      targetDomain: selectedDomain?.domainName,
      targetDC: selectedDomain?.dcName,
    }

    try {
      const response = await fetch(GlobalConfigs.generateRandomUsersEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const result = await response.json()

      // Update operation as succeeded
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "succeeded",
                message: `Successfully generated ${
                  result.users?.length || numUsers
                } random users`,
                details: { ...op.details, usersCreated: result.users },
              }
            : op
        )
      )

      // Update available users list with newly created users
      if (result.users && Array.isArray(result.users)) {
        const domain =
          result.domain || selectedDomain?.domainName || "root domain"
        setAvailableUsers((prev) => {
          const newUsers = result.users
            .filter(
              (u: string) => !prev.some((existing) => getUserName(existing) === u)
            )
            .map((u: string) => ({ username: u, domain, dc: selectedDomain?.dcName || '' }))
          return [...prev, ...newUsers]
        })
      }
    } catch (error) {
      console.error("An error occurred:", error)
      // Update operation as failed
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "failed",
                error: error instanceof Error ? error.message : String(error),
              }
            : op
        )
      )
    } finally {
      setActiveOperationId(null)
    }
  }

  const handleSingleUser = async (event) => {
    event.preventDefault()
    const operationId = `single-${Date.now()}`

    // Add operation to tracking
    const newOperation: UserOperation = {
      id: operationId,
      type: "single-user",
      status: "running",
      message: `Creating user '${singleUsername}' in ${
        selectedDomain?.domainName || "root domain"
      }`,
      timestamp: Date.now(),
      details: { username: singleUsername, domain: selectedDomain?.domainName },
    }

    setUserOperations((prev) => [...prev, newOperation])
    setActiveOperationId(operationId)

    const data = {
      deploymentID,
      singleUsername,
      singleUserPassword: singleUserPasswordForUserGen,
      targetDomain: selectedDomain?.domainName,
      targetDC: selectedDomain?.dcName,
    }

    try {
      const response = await fetch(GlobalConfigs.createSingleUserEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const result = await response.json()

      // Update operation as succeeded
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "succeeded",
                message: `Successfully created user '${singleUsername}'`,
                details: {
                  ...op.details,
                  usersCreated: result.user ? [result.user] : [],
                },
              }
            : op
        )
      )

      // Update available users list with newly created user
      if (result.user) {
        const domain =
          result.domain || selectedDomain?.domainName || "root domain"
        const userExists = availableUsers.some(
          (u) => getUserName(u) === result.user
        )
        if (!userExists) {
          setAvailableUsers((prev) => [
            ...prev,
            { username: result.user, domain, dc: selectedDomain?.dcName || '' },
          ])
        }
      }
    } catch (error) {
      console.error("An error occurred:", error)
      // Update operation as failed
      setUserOperations((prev) =>
        prev.map((op) =>
          op.id === operationId
            ? {
                ...op,
                status: "failed",
                error: error instanceof Error ? error.message : String(error),
              }
            : op
        )
      )
    } finally {
      setActiveOperationId(null)
    }
  }

  const handleFixedCtfSubmit = async (event) => {
    event.preventDefault()
    setLoading(true) // Set loading state to true
    const data = {
      deploymentID,
      targetBox: targetBoxForCtf,
    }

    try {
      const response = await fetch(GlobalConfigs.createFixedCTF1Endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error("Failed to generate users")
      }

      const result = await response.json()
      // Optionally handle success
    } catch (error) {
      console.error("An error occurred:", error)
    } finally {
      setLoading(false) // Set loading state to false
    }
  }

  const handleRandomCtfSubmit = async (event) => {
    event.preventDefault()
    setLoading(true) // Set loading state to true
    const data = {
      deploymentID,
      targetBox: targetBoxForCtf,
      numberOfUsers: parseInt(numberOfUsers, 10),
      difficulty,
    }

    try {
      const response = await fetch(GlobalConfigs.createRandomCtfEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error("Failed to generate users")
      }

      const result = await response.json()
      // Optionally handle success
    } catch (error) {
      console.error("An error occurred:", error)
    } finally {
      setLoading(false) // Set loading state to false
    }
  }

  // Walkthrough step completion handling
  const [completedSteps, setCompletedSteps] = useState([
    false,
    false,
    false,
    false,
  ])
  const [showHints, setShowHints] = useState([false, false, false, false])

  const handleCompletion = (index) => {
    const newCompletedSteps = [...completedSteps]
    newCompletedSteps[index] = true
    setCompletedSteps(newCompletedSteps)
  }

  const toggleHint = (index) => {
    const newShowHints = [...showHints]
    newShowHints[index] = !newShowHints[index]
    setShowHints(newShowHints)
  }

  return (
    <>
      {loading && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Loading />
        </div>
      )}
      <div>
        <h1 className="heading-lg text-center">Info and Config</h1>
        <TabGroup
          className="info-and-config-tab-group-container"
          onChange={handleTabChange}
        >
          <TabList className="flex justify-center mt-2">
            <Tab className="base-button">Network Topology</Tab>
            <Tab className="base-button">Information</Tab>
            <Tab
              className={
                pageLocation === "DEPLOY"
                  ? "base-button opacity-50 cursor-not-allowed"
                  : "base-button"
              }
              disabled={pageLocation === "DEPLOY"}
            >
              Attacks
            </Tab>
            <Tab
              className={
                pageLocation === "DEPLOY"
                  ? "base-button opacity-50 cursor-not-allowed"
                  : "base-button"
              }
              disabled={pageLocation === "DEPLOY"}
            >
              Configuration
            </Tab>
          </TabList>
          <TabPanels className="info-and-config-tab-panels">
            <TabPanel>
              {scenarioInfo === null || scenarioInfo.info === "" ? (
                <div className="">No Environment</div>
              ) : (
                <div>
                  {scenarioInfo ? (
                    <>
                      <div>
                        <TopologyVisualization
                          key={incomingSelectedScenarioFromParent || scenario}
                          deploymentID={
                            pageLocation === "DEPLOY" ||
                            pageLocation === "LOAD_DEPLOYMENT"
                              ? ""
                              : deployID
                          }
                          scenarioName={
                            incomingSelectedScenarioFromParent || scenario
                          }
                        />
                      </div>
                    </>
                  ) : (
                    <div>No data available</div>
                  )}
                </div>
              )}
            </TabPanel>
            <TabPanel>
              {scenarioInfo === null ||
              !scenarioInfo.info ||
              scenarioInfo.info === "" ? (
                <div>No information set for this Environment</div>
              ) : (
                <div className="text-description">
                  <p>
                    {scenarioInfo.savedInfo
                      ? scenarioInfo.savedInfo
                      : scenarioInfo.info}
                  </p>
                </div>
              )}
            </TabPanel>
            <TabPanel>
              <form onSubmit={handleSubmit}>
                <div className="tab-panel-scrollable">
                  {scenarioInfo === null || scenarioInfo.info === "" ? (
                    <div>No Environment</div>
                  ) : deployed === false &&
                    pageLocation !== "DEPLOY" &&
                    pageLocation !== "LOAD_DEPLOYMENT" ? (
                    <div>
                      Environment currently deploying.<br></br> Please wait for
                      deployment to complete.
                    </div>
                  ) : (
                    <>
                      {/* Attacks In Progress Section */}
                      {Object.keys(attacksInProgress).length > 0 && (
                        <div className="mb-6">
                          <h1 className="heading-sm mb-4">Enabling Attacks</h1>
                          <div className="space-y-3">
                            {Object.entries(attacksInProgress)?.map(
                              ([key, value]) => (
                                <Disclosure
                                  key={`progress-${key}-${disclosureResetKey}`}
                                >
                                  {({ open }) => (
                                    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                                      <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors bg-yellow-900/20 border-b border-yellow-700/30">
                                        <div className="text-left">
                                          <div className="flex items-center gap-2">
                                            <h2 className="text-base font-semibold text-yellow-300">
                                              {value.title}
                                            </h2>
                                            <span className="text-xs text-yellow-400 animate-pulse">
                                              In Progress
                                            </span>
                                          </div>
                                          {value.instances &&
                                            value.instances.length > 0 && (
                                              <p className="text-xs text-yellow-400/80 mt-1">
                                                {value.instances
                                                  .map((inst) => {
                                                    const userDisplay =
                                                      formatUserDisplay(
                                                        inst.targetUser
                                                      )
                                                    if (
                                                      userDisplay &&
                                                      inst.targetBox
                                                    ) {
                                                      return `${userDisplay} on ${inst.targetBox}`
                                                    }
                                                    return (
                                                      userDisplay ||
                                                      inst.targetBox
                                                    )
                                                  })
                                                  .filter(Boolean)
                                                  .join(", ")}
                                              </p>
                                            )}
                                        </div>
                                        <svg
                                          className={`w-5 h-5 text-yellow-400 transition-transform ${
                                            open ? "rotate-180" : ""
                                          }`}
                                          fill="none"
                                          viewBox="0 0 24 24"
                                          stroke="currentColor"
                                        >
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M19 9l-7 7-7-7"
                                          />
                                        </svg>
                                      </DisclosureButton>
                                      <DisclosurePanel className="px-6 py-4 bg-slate-900/50">
                                        <div className="text-slate-300 text-sm">
                                          {value.info}
                                          {value.instances &&
                                            value.instances.length > 0 && (
                                              <div className="mt-3">
                                                <strong className="text-slate-200">
                                                  Targets:
                                                </strong>
                                                <ul className="list-disc list-inside mt-1">
                                                  {value.instances.map(
                                                    (inst, idx) => (
                                                      <li key={idx}>
                                                        {inst.targetUser &&
                                                        inst.targetBox
                                                          ? `${inst.targetUser} on ${inst.targetBox}`
                                                          : inst.targetUser ||
                                                            inst.targetBox ||
                                                            "No target specified"}
                                                      </li>
                                                    )
                                                  )}
                                                </ul>
                                              </div>
                                            )}
                                        </div>
                                      </DisclosurePanel>
                                    </div>
                                  )}
                                </Disclosure>
                              )
                            )}
                          </div>
                        </div>
                      )}

                      {/* Enabled Attacks Section */}
                      <div className="mb-6">
                        <h1 className="heading-sm mb-4">Enabled Attacks</h1>
                        {enabledAttacks === "Could not get enabled attacks" ||
                        enabledAttacks === "Could not load deployment" ? (
                          <p className="text-red-400 text-sm">
                            No attacks enabled
                          </p>
                        ) : Object.keys(enabledAttacks).length === 0 ? (
                          <p className="text-slate-400 text-sm">
                            No attacks enabled yet
                          </p>
                        ) : (
                          <div className="max-h-64 overflow-y-auto space-y-3">
                            {Object.entries(enabledAttacks)?.map(
                              ([key, value]) => (
                                <Disclosure
                                  key={`enabled-${key}-${disclosureResetKey}`}
                                >
                                  {({ open }) => (
                                    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                                      <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors">
                                        <div className="text-left">
                                          <div className="flex items-center gap-2">
                                            <h2 className="text-base font-semibold text-slate-50">
                                              {value.title}
                                            </h2>
                                            <span className="text-xs text-green-400">
                                              Enabled
                                            </span>
                                          </div>
                                          {value.instances &&
                                            value.instances.length > 0 && (
                                              <p className="text-xs text-slate-400 mt-1">
                                                {value.instances
                                                  .map((inst) => {
                                                    const userDisplay =
                                                      formatUserDisplay(
                                                        inst.targetUser
                                                      )
                                                    if (
                                                      userDisplay &&
                                                      inst.targetBox
                                                    ) {
                                                      return `${userDisplay} on ${inst.targetBox}`
                                                    }
                                                    return (
                                                      userDisplay ||
                                                      inst.targetBox
                                                    )
                                                  })
                                                  .filter(Boolean)
                                                  .join(", ")}
                                              </p>
                                            )}
                                        </div>
                                        <svg
                                          className={`w-5 h-5 text-slate-400 transition-transform ${
                                            open ? "rotate-180" : ""
                                          }`}
                                          fill="none"
                                          viewBox="0 0 24 24"
                                          stroke="currentColor"
                                        >
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M19 9l-7 7-7-7"
                                          />
                                        </svg>
                                      </DisclosureButton>
                                      <DisclosurePanel className="px-6 py-4 bg-slate-900/50">
                                        <div className="text-slate-300 text-sm">
                                          {value.info}
                                          {value.instances &&
                                            value.instances.length > 0 && (
                                              <div className="mt-3">
                                                <strong className="text-slate-200">
                                                  Enabled for:
                                                </strong>
                                                <ul className="list-disc list-inside mt-1">
                                                  {value.instances.map(
                                                    (inst, idx) => {
                                                      const userDisplay =
                                                        formatUserDisplay(
                                                          inst.targetUser
                                                        )
                                                      return (
                                                        <li key={idx}>
                                                          {userDisplay &&
                                                          inst.targetBox
                                                            ? `${userDisplay} on ${inst.targetBox}`
                                                            : userDisplay ||
                                                              inst.targetBox ||
                                                              "No target specified"}
                                                        </li>
                                                      )
                                                    }
                                                  )}
                                                </ul>
                                              </div>
                                            )}
                                        </div>
                                      </DisclosurePanel>
                                    </div>
                                  )}
                                </Disclosure>
                              )
                            )}
                          </div>
                        )}
                      </div>
                      <h1 className="heading-sm mb-4">Applicable Attacks</h1>
                      <p className="text-xs italic text-slate-400 mb-4">
                        Note: Modifying, enabling, or disabling attacks manually outside of Auto Infra will not be reflected in Auto Infra's tracking.
                      </p>
                      <div className="space-y-3">
                        {Object.entries(applicableAttackData)?.map(
                          ([key, value]) => (
                            <Disclosure key={`${key}-${disclosureResetKey}`}>
                              {({ open }) => (
                                <div
                                  className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden"
                                  key={key}
                                >
                                  <div className="flex items-center gap-3">
                                    <div className="flex-1">
                                      <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors">
                                        <h2 className="text-base font-semibold text-slate-50">
                                          {value.title}
                                        </h2>
                                        <svg
                                          className={`w-5 h-5 text-slate-400 transition-transform ${
                                            open ? "rotate-180" : ""
                                          }`}
                                          fill="none"
                                          viewBox="0 0 24 24"
                                          stroke="currentColor"
                                        >
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M19 9l-7 7-7-7"
                                          />
                                        </svg>
                                      </DisclosureButton>
                                    </div>
                                    <input
                                      type="checkbox"
                                      className="checkbox border-slate-50 [--chkbg:theme(colors.red.900)] checkbox-sm mr-4"
                                      checked={checkboxStates[key]}
                                      disabled={
                                        pageLocation === "DEPLOY" ||
                                        loading === true ||
                                        pageLocation === "LOAD_DEPLOYMENT"
                                      }
                                      onChange={() => handleCheckboxChange(key)}
                                    />
                                  </div>
                                  <DisclosurePanel className="px-6 py-4 bg-slate-900/50">
                                    <div className="text-slate-300 text-sm">
                                      {value.info}
                                      {value.requiresUser &&
                                        pageLocation !== "DEPLOY" &&
                                        pageLocation !== "LOAD_DEPLOYMENT" && (
                                          <>
                                            <div className="mb-4">
                                              <label className="block text-slate-200 font-semibold text-sm mb-2">
                                                Target User:
                                              </label>
                                              {availableUsers.length > 0 ? (
                                                <select
                                                  value={targetUser[key] || ""}
                                                  onChange={(e) =>
                                                    setTargetUser({
                                                      ...targetUser,
                                                      [key]: e.target.value,
                                                    })
                                                  }
                                                  className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                                  required
                                                >
                                                  <option value="">
                                                    Select a user...
                                                  </option>
                                                  {availableUsers.map(
                                                    (user) => (
                                                      <option
                                                        key={
                                                          getUserName(user)
                                                        }
                                                        value={getUserDisplayName(
                                                          user
                                                        )}
                                                      >
                                                        {getUserDisplayName(
                                                          user
                                                        )}
                                                      </option>
                                                    )
                                                  )}
                                                </select>
                                              ) : (
                                                <div className="text-amber-400 text-sm">
                                                  No users available. Create
                                                  users first in the
                                                  Configuration tab.
                                                </div>
                                              )}
                                            </div>
                                            {value.requiresTargetBox && (
                                              <div className="mb-4">
                                                <label className="block text-slate-200 font-semibold text-sm mb-2">
                                                  Target Machine:
                                                </label>
                                                {availableMachines.length >
                                                0 ? (
                                                  <select
                                                    value={
                                                      targetMachine[key] || ""
                                                    }
                                                    onChange={(e) =>
                                                      setTargetMachine({
                                                        ...targetMachine,
                                                        [key]: e.target.value,
                                                      })
                                                    }
                                                    className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                                    required
                                                  >
                                                    <option value="">
                                                      Select a machine...
                                                    </option>
                                                    {availableMachines.map(
                                                      (machine) => (
                                                        <option
                                                          key={
                                                            machine.machineName
                                                          }
                                                          value={
                                                            machine.machineName
                                                          }
                                                        >
                                                          {machine.displayName}
                                                        </option>
                                                      )
                                                    )}
                                                  </select>
                                                ) : (
                                                  <div className="text-amber-400 text-sm">
                                                    No machines available.
                                                  </div>
                                                )}
                                              </div>
                                            )}
                                            {value.requiresSingleUserPassword && (
                                              <div className="mb-4">
                                                <label className="block text-slate-200 font-semibold text-sm mb-2">
                                                  Single User Password:
                                                </label>
                                                <input
                                                  type="text"
                                                  value={
                                                    singleUserPassword[key] ||
                                                    ""
                                                  }
                                                  onChange={(e) =>
                                                    setsingleUserPassword({
                                                      ...singleUserPassword,
                                                      [key]: e.target.value,
                                                    })
                                                  }
                                                  className="input input-bordered w-full bg-slate-800 border-slate-600 text-white"
                                                  required
                                                />
                                              </div>
                                            )}
                                          </>
                                        )}
                                      {value.requiresGrantingUser &&
                                        pageLocation !== "DEPLOY" &&
                                        pageLocation !== "LOAD_DEPLOYMENT" && (
                                          <>
                                            <div className="mb-4">
                                              <label className="block text-slate-200 font-semibold text-sm mb-2">
                                                Granting User (gets
                                                permissions):
                                              </label>
                                              {availableUsers.length > 0 ? (
                                                <select
                                                  value={
                                                    grantingUser[key] || ""
                                                  }
                                                  onChange={(e) =>
                                                    setGrantingUser({
                                                      ...grantingUser,
                                                      [key]: e.target.value,
                                                    })
                                                  }
                                                  className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                                  required
                                                >
                                                  <option value="">
                                                    Select a user...
                                                  </option>
                                                  {availableUsers.map(
                                                    (user) => (
                                                      <option
                                                        key={
                                                          getUserName(user)
                                                        }
                                                        value={getUserDisplayName(
                                                          user
                                                        )}
                                                      >
                                                        {getUserDisplayName(
                                                          user
                                                        )}
                                                      </option>
                                                    )
                                                  )}
                                                </select>
                                              ) : (
                                                <div className="text-amber-400 text-sm">
                                                  No users available. Create
                                                  users first in the
                                                  Configuration tab.
                                                </div>
                                              )}
                                            </div>
                                            {value.requiresReceivingUser && (
                                              <div className="mb-4">
                                                <label className="block text-slate-200 font-semibold text-sm mb-2">
                                                  Receiving User (grants
                                                  permissions):
                                                </label>
                                                {availableUsers.length > 0 ? (
                                                  <select
                                                    value={
                                                      receivingUser[key] || ""
                                                    }
                                                    onChange={(e) =>
                                                      setReceivingUser({
                                                        ...receivingUser,
                                                        [key]: e.target.value,
                                                      })
                                                    }
                                                    className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                                    required
                                                  >
                                                    <option value="">
                                                      Select a user...
                                                    </option>
                                                    {availableUsers.map(
                                                      (user) => (
                                                        <option
                                                          key={
                                                            getUserName(user)
                                                          }
                                                          value={getUserDisplayName(
                                                            user
                                                          )}
                                                        >
                                                          {getUserDisplayName(
                                                            user
                                                          )}
                                                        </option>
                                                      )
                                                    )}
                                                  </select>
                                                ) : (
                                                  <div className="text-amber-400 text-sm">
                                                    No users available. Create
                                                    users first in the
                                                    Configuration tab.
                                                  </div>
                                                )}
                                              </div>
                                            )}
                                          </>
                                        )}
                                    </div>
                                  </DisclosurePanel>
                                </div>
                              )}
                            </Disclosure>
                          )
                        )}
                      </div>
                      <button
                        type="submit"
                        className="base-button pt-4 mx-[13rem]"
                        disabled={attacksEnabling || pageLocation === "DEPLOY"}
                      >
                        {attacksEnabling ||
                        Object.keys(attacksInProgress).length > 0
                          ? Object.keys(attacksInProgress).length > 0
                            ? `Enabling: ${Object.values(attacksInProgress)
                                .map((a) => a.title)
                                .join(", ")}`
                            : "Enabling attack(s)..."
                          : "Submit"}
                      </button>
                    </>
                  )}
                </div>
              </form>
            </TabPanel>
            <TabPanel>
              {scenarioInfo === null || scenarioInfo.info === "" ? (
                <div>No Environment</div>
              ) : pageLocation === "HOME" && deployed === false ? (
                <div>
                  Environment currently deploying.<br></br> Please wait for
                  deployment to complete.
                </div>
              ) : (
                <div className="tab-panel-scrollable">
                  {/* Existing Users Panel */}
                  {availableUsers.length > 0 && (
                    <div className="bg-slate-800 rounded-lg border border-slate-700 p-5 mb-6">
                      <h3 className="text-lg font-semibold text-slate-50 mb-3">
                        Existing Users ({availableUsers.length})
                      </h3>
                      <div className="max-h-48 overflow-y-auto">
                        {Object.entries(
                          availableUsers.reduce((acc, user) => {
                            // Handle multiple formats: string, {domain, username}, or {dc, domain, username}
                            if (typeof user === 'string') {
                              // Legacy string format - use a default domain
                              if (!acc['Legacy']) acc['Legacy'] = []
                              acc['Legacy'].push(user)
                            } else if (typeof user === 'object' && user !== null) {
                              // Object format - extract username and domain
                              const username = user.username || ''
                              const domain = user.domain || 'Unknown'
                              
                              if (username) {
                                if (!acc[domain]) acc[domain] = []
                                acc[domain].push(username)
                              }
                            }
                            return acc
                          }, {} as Record<string, string[]>)
                        ).map(([domain, users]) => (
                          <div key={domain} className="mb-4 last:mb-0">
                            <div className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
                              {domain}
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                              {users.map((username) => {
                                // username is guaranteed to be a string by the reduce operation
                                return (
                                  <div
                                    key={`${domain}-${username}`}
                                    className="bg-slate-900/50 border border-slate-700 rounded px-3 py-2 text-center"
                                    title={`${username}@${domain}`}
                                  >
                                    <div className="text-sm text-slate-300 font-mono">
                                      {username}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Sync Users Button */}
                  <div className="mb-6 flex justify-end">
                    <button
                      type="button"
                      onClick={syncUsersFromAD}
                      disabled={isSyncingUsers}
                      className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                        isSyncingUsers
                          ? "bg-slate-600 text-slate-400 cursor-not-allowed"
                          : "bg-blue-600 text-white hover:bg-blue-700"
                      }`}
                      title="Query all domain controllers to sync users from Active Directory"
                    >
                      {isSyncingUsers ? (
                        <>
                          <svg className="animate-spin inline-block w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                          Syncing...
                        </>
                      ) : (
                        <>
                          <svg className="inline-block w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          Sync Users from AD
                        </>
                      )}
                    </button>
                  </div>
                  
                  <h1 className="heading-sm mb-4">Generate Users</h1>
                  <div className="space-y-4">
                    <Disclosure>
                      {({ open }) => (
                        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                          <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors">
                            <div className="text-left">
                              <h2 className="text-lg font-semibold text-slate-50">
                                Generate Fixed Users
                              </h2>
                              <p className="text-sm text-slate-400 mt-0.5">
                                Creates 25 preset users (User1-User24 and
                                EntryUser)
                              </p>
                            </div>
                            <svg
                              className={`w-5 h-5 text-slate-400 transition-transform ${
                                open ? "rotate-180" : ""
                              }`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </DisclosureButton>
                          <DisclosurePanel className="px-6 pb-6">
                            {activeOperationId?.startsWith("fixed-") ? (
                              <div className="bg-slate-900/50 rounded-lg border border-slate-700 p-4">
                                <div className="flex items-center justify-between p-3 rounded bg-yellow-900/20 border border-yellow-700/30">
                                  <span className="text-sm font-mono text-yellow-300">
                                    Generating fixed users in{" "}
                                    {selectedDomain?.domainName ||
                                      "root domain"}
                                    ...
                                  </span>
                                  <span className="text-xs text-yellow-400 animate-pulse">
                                    In Progress
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <form
                                onSubmit={handleGenerateUsers}
                                className="space-y-4"
                              >
                                {availableDomains.length > 1 && (
                                  <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                      Target Domain
                                    </label>
                                    <select
                                      value={selectedDomain?.domainName || ""}
                                      onChange={(e) => {
                                        const domain = availableDomains.find(
                                          (d) => d.domainName === e.target.value
                                        )
                                        if (domain) {
                                          setSelectedDomain({
                                            domainName: domain.domainName,
                                            dcName: domain.dcName,
                                          })
                                        }
                                      }}
                                      className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    >
                                      {availableDomains.map((domain) => (
                                        <option
                                          key={domain.domainName}
                                          value={domain.domainName}
                                        >
                                          {domain.domainName}{" "}
                                          {domain.isRoot ? "(Root)" : ""}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                )}
                                <div className="flex justify-center">
                                  <button
                                    type="submit"
                                    className="mt-2 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
                                  >
                                    Generate Fixed Users
                                  </button>
                                </div>
                              </form>
                            )}
                          </DisclosurePanel>
                        </div>
                      )}
                    </Disclosure>

                    <Disclosure>
                      {({ open }) => (
                        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                          <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors">
                            <div className="text-left">
                              <h2 className="text-lg font-semibold text-slate-50">
                                Create Single User
                              </h2>
                              <p className="text-sm text-slate-400 mt-0.5">
                                Create a custom user with your own credentials
                              </p>
                            </div>
                            <svg
                              className={`w-5 h-5 text-slate-400 transition-transform ${
                                open ? "rotate-180" : ""
                              }`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </DisclosureButton>
                          <DisclosurePanel className="px-6 pb-6">
                            {activeOperationId?.startsWith("single-") ? (
                              <div className="bg-slate-900/50 rounded-lg border border-slate-700 p-4">
                                <div className="flex items-center justify-between p-3 rounded bg-yellow-900/20 border border-yellow-700/30">
                                  <span className="text-sm font-mono text-yellow-300">
                                    Creating user '{singleUsername}' in{" "}
                                    {selectedDomain?.domainName ||
                                      "root domain"}
                                    ...
                                  </span>
                                  <span className="text-xs text-yellow-400 animate-pulse">
                                    In Progress
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <form
                                onSubmit={handleSingleUser}
                                className="space-y-4"
                              >
                                {availableDomains.length > 1 && (
                                  <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                      Target Domain
                                    </label>
                                    <select
                                      value={selectedDomain?.domainName || ""}
                                      onChange={(e) => {
                                        const domain = availableDomains.find(
                                          (d) => d.domainName === e.target.value
                                        )
                                        if (domain) {
                                          setSelectedDomain({
                                            domainName: domain.domainName,
                                            dcName: domain.dcName,
                                          })
                                        }
                                      }}
                                      className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    >
                                      {availableDomains.map((domain) => (
                                        <option
                                          key={domain.domainName}
                                          value={domain.domainName}
                                        >
                                          {domain.domainName}{" "}
                                          {domain.isRoot ? "(Root)" : ""}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                )}
                                <div>
                                  <label className="block text-sm font-medium text-neutral-300 mb-2">
                                    Username
                                  </label>
                                  <input
                                    type="text"
                                    value={singleUsername}
                                    onChange={(e) =>
                                      setsingleUsername(e.target.value)
                                    }
                                    className="input input-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    placeholder="Enter username"
                                    required
                                  />
                                </div>
                                <div>
                                  <label className="block text-sm font-medium text-neutral-300 mb-2">
                                    Password
                                  </label>
                                  <input
                                    type="password"
                                    value={singleUserPasswordForUserGen}
                                    onChange={(e) =>
                                      setsingleUserPasswordForUserGen(
                                        e.target.value
                                      )
                                    }
                                    className="input input-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    placeholder="Enter password"
                                    required
                                  />
                                </div>
                                <div className="flex justify-center">
                                  <button
                                    type="submit"
                                    className="mt-2 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
                                  >
                                    Create Single User
                                  </button>
                                </div>
                              </form>
                            )}
                          </DisclosurePanel>
                        </div>
                      )}
                    </Disclosure>

                    <Disclosure>
                      {({ open }) => (
                        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                          <DisclosureButton className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700 transition-colors">
                            <div className="text-left">
                              <h2 className="text-lg font-semibold text-slate-50">
                                Generate Random Users
                              </h2>
                              <p className="text-sm text-slate-400 mt-0.5">
                                Create a specified number of randomly generated
                                users
                              </p>
                            </div>
                            <svg
                              className={`w-5 h-5 text-slate-400 transition-transform ${
                                open ? "rotate-180" : ""
                              }`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </DisclosureButton>
                          <DisclosurePanel className="px-6 pb-6">
                            {activeOperationId?.startsWith("random-") ? (
                              <div className="bg-slate-900/50 rounded-lg border border-slate-700 p-4">
                                <div className="flex items-center justify-between p-3 rounded bg-yellow-900/20 border border-yellow-700/30">
                                  <span className="text-sm font-mono text-yellow-300">
                                    Generating {numberOfUsers} random users in{" "}
                                    {selectedDomain?.domainName ||
                                      "root domain"}
                                    ...
                                  </span>
                                  <span className="text-xs text-yellow-400 animate-pulse">
                                    In Progress
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <form
                                onSubmit={handleGenerateRandomUsers}
                                className="space-y-4"
                              >
                                {availableDomains.length > 1 && (
                                  <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                      Target Domain
                                    </label>
                                    <select
                                      value={selectedDomain?.domainName || ""}
                                      onChange={(e) => {
                                        const domain = availableDomains.find(
                                          (d) => d.domainName === e.target.value
                                        )
                                        if (domain) {
                                          setSelectedDomain({
                                            domainName: domain.domainName,
                                            dcName: domain.dcName,
                                          })
                                        }
                                      }}
                                      className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    >
                                      {availableDomains.map((domain) => (
                                        <option
                                          key={domain.domainName}
                                          value={domain.domainName}
                                        >
                                          {domain.domainName}{" "}
                                          {domain.isRoot ? "(Root)" : ""}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                )}
                                <div>
                                  <label className="block text-sm font-medium text-neutral-300 mb-2">
                                    Username Format
                                  </label>
                                  <select
                                    value={usernameFormat}
                                    onChange={(e) =>
                                      setUsernameFormat(e.target.value)
                                    }
                                    className="select select-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    required
                                  >
                                    <option value="firstname">
                                      First Name Only (e.g., john)
                                    </option>
                                    <option value="firstname.lastname">
                                      First.Last (e.g., john.doe)
                                    </option>
                                    <option value="firstinitial.lastname">
                                      FirstInitialLast (e.g., jdoe)
                                    </option>
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-sm font-medium text-neutral-300 mb-2">
                                    Number of Users
                                  </label>
                                  <input
                                    type="number"
                                    min="1"
                                    max="100"
                                    value={numberOfUsers}
                                    onChange={(e) =>
                                      setnumberOfUsers(e.target.value)
                                    }
                                    className="input input-bordered w-full bg-slate-800 border-slate-600 text-white"
                                    placeholder="e.g. 10"
                                    required
                                  />
                                </div>
                                <div className="flex justify-center">
                                  <button
                                    type="submit"
                                    className="mt-2 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
                                  >
                                    Generate Random Users
                                  </button>
                                </div>
                              </form>
                            )}
                          </DisclosurePanel>
                        </div>
                      )}
                    </Disclosure>
                  </div>
                  {/* TODO: Re-enable CTF configuration
                  <h1 className="heading-sm mt-4">Generate CTF</h1>
                  <Disclosure>
                    <DisclosureButton className="w-full">
                      <div className="label base-button w-[95%]">
                        <span className="text-neutral-50">Fixed CTF 1</span>
                      </div>
                    </DisclosureButton>
                    <DisclosurePanel className="info-and-config-configuration-panel">
                      <p className="mb-4">
                        This will deploy a CTF from low level user to domain
                        admin. This utilizes Generate Fixed Users and the user
                        must start by logging into EntryUser. The attack path is
                        Local priv esc, dump hashes, utilize hash of certain
                        user, exploit constrained delegation, escalate to domain
                        and beyond.
                      </p>
                      <form onSubmit={handleFixedCtfSubmit}>
                        <div className="mb-4">
                          <label className="block text-neutral-50 font-bold mb-2">
                            Target Box to Run this on (Recommended to run on
                            workstation: EntryPoint):
                          </label>
                          <input
                            type="text"
                            value={targetBoxForCtf}
                            onChange={(e) => setTargetBoxForCtf(e.target.value)}
                            className="bg-neutral-800 text-neutral-50 border border-neutral-700 rounded w-full py-2 px-3"
                            required
                          />
                        </div>
                        <button
                          type="submit"
                          className="base-button py-2 px-4"
                          disabled={loading}
                        >
                          {loading
                            ? "Please wait 5 to 10 minutes..."
                            : "Fixed CTF1"}
                        </button>
                      </form>
                    </DisclosurePanel>
                  </Disclosure>
                  <Disclosure>
                    <DisclosureButton className="w-full">
                      <div className="label base-button w-[95%]">
                        <span className="text-neutral-50">Random CTF</span>
                      </div>
                    </DisclosureButton>
                    <DisclosurePanel className="info-and-config-configuration-panel">
                      <p className="mb-4">
                        This will deploy a random CTF on desired environment
                        based on chosen difficulty. The user can dictate how
                        many random users are created. Easy: 2 attacks enabled.
                        Medium: 3 attacks enabled. Hard: 4 attacks enabled. All
                        attack chains will lead to domain admin.
                      </p>
                      <form onSubmit={handleRandomCtfSubmit}>
                        <div className="mb-4">
                          <label className="block text-neutral-50 font-bold mb-2">
                            Target Box to Run this on (Recommended to run on
                            workstation: EntryPoint):
                          </label>
                          <input
                            type="text"
                            value={targetBoxForCtf}
                            onChange={(e) => setTargetBoxForCtf(e.target.value)}
                            className="bg-neutral-800 text-neutral-50 border border-neutral-700 rounded w-full py-2 px-3"
                            required
                          />
                        </div>
                        <div className="mb-4">
                          <label className="block text-neutral-50 font-bold mb-2">
                            Number of Users:
                          </label>
                          <input
                            type="text"
                            value={numberOfUsers}
                            onChange={(e) => setnumberOfUsers(e.target.value)}
                            className="bg-neutral-800 text-neutral-50 border border-neutral-700 rounded w-full py-2 px-3"
                            required
                          />
                        </div>
                        <div className="mb-4">
                          <label className="block text-neutral-50 font-bold mb-2">
                            Difficulty:
                          </label>
                          <select
                            value={difficulty}
                            onChange={(e) => setDifficulty(e.target.value)}
                            className="bg-neutral-800 text-neutral-50 border border-neutral-700 rounded w-full py-2 px-3"
                            required
                          >
                            <option value="">Select Difficulty</option>
                            <option value="easy">Easy</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard</option>
                          </select>
                        </div>
                        <button
                          type="submit"
                          className="base-button py-2 px-4"
                          disabled={loading}
                        >
                          {loading
                            ? "Please wait 5 to 10 minutes..."
                            : "Random CTF"}
                        </button>
                      </form>
                    </DisclosurePanel>
                  </Disclosure>
                  */}
                </div>
              )}
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </>
  )
}
