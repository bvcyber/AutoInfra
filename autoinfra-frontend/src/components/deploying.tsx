"use client";
import { GetCookie, DeleteCookie } from "./cookieHandler";
import { FetchEnvironmentState } from "./fetchEnvironmentState";
import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import GlobalConfigs from "@/app/app.config";

interface DeploymentDetails {
  running: string[];
  succeeded: string[];
  failed?: string[];
}

interface DeploymentItem {
  name: string;
  status: "running" | "succeeded" | "failed" | "pending";
}

export default function Deploying({ customMessage }: { customMessage?: string }) {
  const deploymentID = GetCookie("deploymentID");
  const [scenario, setScenario] = useState("");
  const [deploymentType, setDeploymentType] = useState("scenario");
  const [checkCount, setCheckCount] = useState(0);
  const [deploymentTimeout, setDeploymentTimeout] = useState(0);
  const [deploymentItems, setDeploymentItems] = useState<DeploymentItem[]>([]);
  const [failureError, setFailureError] = useState<string | null>(null);
  const router = useRouter();

  // Detect if this is a build deployment based on ID pattern
  const isBuildDeployment = deploymentID && deploymentID.startsWith("BuildLab-");

  const getInfo = async () => {
    try {
      const response = await fetch(GlobalConfigs.getDeploymentInfoEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          deploymentID,
          isBuildDeployment
        }),
      });
      
      if (!response.ok) {
        return { message: null };
      }
      
      return await response.json();
    } catch (error) {
      console.error("Error getting deployment info:", error);
      return { message: null };
    }
  };

  useEffect(() => {
    const getInfoEffect = async () => {
      if (deploymentID !== "error" && deploymentID) {
        try {
          const data = await getInfo();
          
          if (data.message && data.message.scenario) {
            setScenario(data.message.scenario);
            setDeploymentType("scenario");
          } else if (data.message && data.message.topology) {
            setScenario("Custom Topology");
            setDeploymentType("topology");
          } else if (isBuildDeployment) {
            // If we can't get specific info but we know it's a build deployment
            setScenario("Custom Topology");
            setDeploymentType("topology");
          }
        } catch (error) {
          console.error("Error fetching deployment info:", error);
          if (isBuildDeployment) {
            setScenario("Custom Topology");
            setDeploymentType("topology");
          }
        }
      }
    };
    getInfoEffect();
    
    // Set a maximum timeout for build deployments (15 minutes)
    if (isBuildDeployment) {
      setDeploymentTimeout(Date.now() + 15 * 60 * 1000);
    }
  }, [deploymentID, isBuildDeployment]);

  // Fetch deployment state with details
  const fetchDeploymentDetails = useCallback(async () => {
    if (!deploymentID) return null;
    
    try {
      const response = await fetch(GlobalConfigs.getDeploymentStateEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deploymentID }),
      });
      
      if (!response.ok) return null;
      
      const data = await response.json();
      const details: DeploymentDetails = data.details || {};
      
      // Build unified list of all deployments with their statuses
      const allItems: DeploymentItem[] = [];
      const seenNames = new Set<string>();
      
      // Add failed deployments
      (details.failed || []).forEach((name: string) => {
        if (!seenNames.has(name)) {
          seenNames.add(name);
          allItems.push({ name, status: "failed" });
        }
      });
      
      // Add running deployments
      (details.running || []).forEach((name: string) => {
        if (!seenNames.has(name)) {
          seenNames.add(name);
          allItems.push({ name, status: "running" });
        }
      });
      
      // Add succeeded deployments
      (details.succeeded || []).forEach((name: string) => {
        if (!seenNames.has(name)) {
          seenNames.add(name);
          allItems.push({ name, status: "succeeded" });
        }
      });
      
      // Sort: running first, then succeeded, then failed
      allItems.sort((a, b) => {
        const order = { running: 0, succeeded: 1, failed: 2, pending: 3 };
        return order[a.status] - order[b.status];
      });

      setDeploymentItems(allItems);

      // If deployment failed, capture the error message
      // This handles both "failed" state and "shutting down" state (when deletion started after failure)
      if (data.error && !failureError) {
        setFailureError(data.error);
      }

      return data.message;
    } catch (error) {
      console.error("Error fetching deployment details:", error);
      return null;
    }
  }, [deploymentID]);

  // Use ref to store latest fetchDeploymentDetails to avoid recreating interval
  const fetchRef = useRef(fetchDeploymentDetails);
  useEffect(() => {
    fetchRef.current = fetchDeploymentDetails;
  }, [fetchDeploymentDetails]);

  // Delete deploymentID cookie when build fails
  useEffect(() => {
    if (failureError) {
      DeleteCookie("deploymentID");
    }
  }, [failureError]);

  useEffect(() => {

    // Fetch immediately on mount
    fetchRef.current();

    const interval = setInterval(async () => {
      setCheckCount(prev => {
        return prev + 1;
      });

      try {
        const state = await fetchRef.current();

        // Check for timeout on build deployments
        if (isBuildDeployment && deploymentTimeout && Date.now() > deploymentTimeout) {
          clearInterval(interval);
          router.push("/");
          return;
        }

        if (state === "deployed") {
          clearInterval(interval);

          // Use setTimeout to ensure state is consistent before redirect
          setTimeout(() => {
            router.push("/");
          }, 1000);
        } else if (state === "failed") {
          clearInterval(interval);
          // Error message is already set by fetchDeploymentDetails
        } else if (state === "shutting down" && failureError) {
          // If we already have an error (build failed) and now it's shutting down (auto-deletion)
          // Stop polling and keep showing the error screen
          clearInterval(interval);
        } else if (state === null || state === undefined) {
        }
      } catch (error) {
        console.error("Error checking environment state:", error);
      }
    }, 5000);  // Check every 5 seconds for better UX

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, isBuildDeployment, deploymentTimeout]);

  // Helper to get status text
  const getStatusText = (status: DeploymentItem["status"]) => {
    switch (status) {
      case "succeeded":
        return "Completed";
      case "running":
        return "In Progress";
      case "failed":
        return "Failed";
      default:
        return "Pending";
    }
  };

  // Helper to get status color
  const getStatusColor = (status: DeploymentItem["status"]) => {
    switch (status) {
      case "succeeded":
        return "text-green-400";
      case "running":
        return "text-yellow-400";
      case "failed":
        return "text-red-400";
      default:
        return "text-neutral-400";
    }
  };

  // Show error screen if deployment failed
  if (failureError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-start pt-24 p-8">
        <h1 className="text-red-400 text-3xl font-extrabold text-center mb-2">
          Build Failed
        </h1>

        <div className="text-neutral-400 text-center mb-6">
          The deployment encountered an error and has been deleted.
        </div>

        <div className="w-full max-w-2xl bg-red-900/20 border border-red-700/50 rounded-lg p-6 mb-6">
          <h3 className="text-red-300 font-semibold mb-3">Error Details:</h3>
          <div className="text-neutral-300 text-sm font-mono whitespace-pre-wrap break-words">
            {failureError}
          </div>
        </div>

        {/* Failed Deployment List */}
        {deploymentItems.length > 0 && (
          <div className="w-full max-w-md bg-neutral-800/50 rounded-lg border border-neutral-700 p-4 mb-6">
            <h3 className="text-neutral-200 font-semibold mb-3 text-center">
              Deployment Status
            </h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {deploymentItems.map((item, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-2 rounded"
                >
                  <span className="text-sm font-mono truncate text-neutral-300">
                    {item.name}
                  </span>
                  <span className={`text-xs ml-3 whitespace-nowrap ${getStatusColor(item.status)}`}>
                    {getStatusText(item.status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={() => router.push("/")}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors"
        >
          Return to Home
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-start pt-24 p-8">
      <h1 className="text-neutral-50 text-3xl font-extrabold text-center mb-2">
        Deploying
      </h1>

      <div className="text-neutral-400 text-center mb-6">
        {customMessage || "Please wait while your environment is being deployed"}
      </div>
      
      <div className="text-neutral-50 text-center mb-8">
        <div className="text-lg font-semibold">
          {deploymentType === "scenario" 
            ? `Scenario: ${scenario}` 
            : `Custom Topology`}
        </div>
        <div className="text-neutral-400 text-sm">
          Resource Group: {deploymentID}
        </div>
      </div>

      {/* Deployment Progress List */}
      {deploymentItems.length > 0 && (
        <div className="w-full max-w-md bg-neutral-800/50 rounded-lg border border-neutral-700 p-4">
          <h3 className="text-neutral-200 font-semibold mb-3 text-center">
            Deployment Progress ({deploymentItems.filter(d => d.status === "succeeded").length}/{deploymentItems.length})
          </h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {deploymentItems.map((item, index) => (
              <div 
                key={index}
                className={`flex items-center justify-between p-2 rounded ${
                  item.status === "running" ? "bg-yellow-900/20 border border-yellow-700/30" : ""
                }`}
              >
                <span className={`text-sm font-mono truncate ${
                  item.status === "succeeded" ? "text-neutral-300" : 
                  item.status === "running" ? "text-yellow-300" : "text-neutral-400"
                }`}>
                  {item.name}
                </span>
                <span className={`text-xs ml-3 whitespace-nowrap ${getStatusColor(item.status)} ${
                  item.status === "running" ? "animate-pulse" : ""
                }`}>
                  {getStatusText(item.status)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Loading spinner when no items yet */}
      {deploymentItems.length === 0 && (
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-neutral-400">Initializing deployment...</span>
        </div>
      )}

      {isBuildDeployment && (
        <div className="text-neutral-400 text-center mt-8 text-sm">
          <p>Building a custom topology may take 10-30 minutes.</p>
          <p>You will be automatically redirected when complete.</p>
        </div>
      )}
    </div>
  );
}
