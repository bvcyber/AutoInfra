"use client"
import { GetCookie, SetCookie } from "./cookieHandler"
import { useDeployments } from "@/contexts/DeploymentContext"

export default function DeployedEnvironments() {
  const { deployments, isLoading } = useDeployments()

  const onClick = (deploymentID: string) => {
    SetCookie("deploymentID", deploymentID)

    setTimeout(() => {
      window.location.href = "/"
    }, 100)
  }

  const currentDeploymentID = GetCookie("deploymentID")

  if (isLoading) {
    return <div className="text-loading">Loading environments...</div>
  }

  return (
    <div className="flex flex-col space-y-2 pt-2 w-full">
      {deployments.length > 0 ? (
        deployments.map((environment) => (
          <div key={environment.id} className="environment-card">
            <div className="flex-flex-col">
              <div className="deployed-environment-scenario">
                {environment.scenario}
              </div>

              <div className="deployed-environment-id">{environment.id}</div>

              {/* Status and Action Button */}
              <div className="flex justify-between items-center">
                <div className="text-sm">
                  {environment.state === "deploying" && (
                    <span className="deployed-environment- status-deploying">
                      Deploying
                    </span>
                  )}
                  {environment.state === "deployed" && (
                    <span className="deployed-environment-status-deployed">
                      Ready
                    </span>
                  )}
                  {environment.state === "saving" && (
                    <span className="deployed-environment-status-saving">
                      Saving
                    </span>
                  )}
                  {environment.state === "shutting down" && (
                    <span className="deployed-environment-status-destroying">
                      Destroying
                    </span>
                  )}
                </div>

                <div>
                  {environment.state !== "shutting down" &&
                    environment.state !== "saving" &&
                    (currentDeploymentID !== environment.id ? (
                      <button
                        className="deployed-environment-interact-label"
                        onClick={() => onClick(environment.id)}
                      >
                        Interact
                      </button>
                    ) : (
                      <button
                        className="deployed-environment-selected-label"
                        disabled
                      >
                        Current
                      </button>
                    ))}
                </div>
              </div>
            </div>
          </div>
        ))
      ) : (
        <div className="text-loading">No deployed environments</div>
      )}
    </div>
  )
}
