"use client"

import { useState, useEffect } from "react"
import GlobalConfig from "../app.config"
import { useAuth } from "@/contexts/AuthContext"

export default function AuthPage() {
  const { refreshAuth } = useAuth()
  const [formData, setFormData] = useState({
    azServicePrincipalID: "",
    azServicePrincipalPassword: "",
    azTenant: "",
    azSubscriptionID: "",
  })
  const [responseMessage, setResponseMessage] = useState("")
  const [isAuthorized, setIsAuthorized] = useState(false)
  const [loading, setLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const checkAuthorization = async () => {
      try {
        const response = await fetch(GlobalConfig.checkAuthEndpoint)
        const data = await response.json()
        setIsAuthorized(data.message === "Authorized")
      } catch (error) {
        console.error("Error checking authorization:", error)
        setIsAuthorized(false)
      } finally {
        setLoading(false)
      }
    }

    checkAuthorization()
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setResponseMessage("")
    setIsSubmitting(true)

    try {
      const response = await fetch(GlobalConfig.azureAuthEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      })

      if (response.ok) {
        const data = await response.json()
        if (data.message === "success") {
          setResponseMessage("")
          setIsAuthorized(true)
          await refreshAuth()
        } else {
          setResponseMessage(data.message || "Failed to authenticate. Please check your credentials.")
        }
      } else {
        setResponseMessage("Failed to authenticate. Please verify your Azure credentials.")
      }
    } catch (error) {
      console.error("Error:", error)
      setResponseMessage("Network error. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  const copyCommand = () => {
    const subscriptionId = formData.azSubscriptionID || "YOUR-SUBSCRIPTION-ID"
    const command = `az ad sp create-for-rbac --name "AutoInfra" --scopes /subscriptions/${subscriptionId} --sdk-auth --role Contributor`
    navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="pinging-red-loader"></div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <h1 className="base-title-centered base-text-color mb-4">
        Azure Configuration
      </h1>

      {/* Status Badge */}
      <div className="flex items-center justify-center gap-2 mb-8">
        <span className="text-slate-400 text-sm">Status:</span>
        {isAuthorized ? (
          <span className="px-3 py-1 bg-green-900/30 border border-green-500 text-green-400 rounded-full text-sm font-semibold">
            Connected
          </span>
        ) : (
          <span className="px-3 py-1 bg-red-900/30 border border-red-500 text-red-400 rounded-full text-sm font-semibold">
            Not Connected
          </span>
        )}
      </div>

      <div className="responsive-two-col gap-6 mb-6">
        {/* Left Column - Setup Instructions */}
        <div className="form-section">
          <h2 className="form-section-title">Quick Setup</h2>

          <div className="space-y-4 text-slate-300">
            <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-4">
              <p className="font-semibold text-slate-50 mb-2">Step 1: Install Azure CLI</p>
              <a
                href="https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
                target="_blank"
                className="text-blue-400 hover:text-blue-300 underline text-sm"
              >
                Download Azure CLI →
              </a>
            </div>

            <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-4">
              <p className="font-semibold text-slate-50 mb-2">Step 2: Get Subscription ID</p>
              <p className="text-sm mb-2">Visit the{" "}
                <a
                  href="https://portal.azure.com/#view/Microsoft_Azure_Billing/SubscriptionsBladeV2"
                  target="_blank"
                  className="text-blue-400 hover:text-blue-300 underline"
                >
                  Azure Portal
                </a>{" "}
                and copy your Subscription ID
              </p>
              <img src="/por1.png" className="rounded-lg border border-slate-700 mt-2" alt="Azure Portal"/>
            </div>

            <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-4">
              <p className="font-semibold text-slate-50 mb-2">Step 3: Create Service Principal</p>
              <p className="text-sm mb-3">Run this command (paste your Subscription ID in the form first):</p>
              <div className="relative">
                <pre className="bg-black text-green-400 p-3 rounded-lg text-xs overflow-x-auto border border-slate-600">
                  {`az ad sp create-for-rbac --name "AutoInfra" \\
  --scopes /subscriptions/${formData.azSubscriptionID || "YOUR-SUBSCRIPTION-ID"} \\
  --sdk-auth --role Contributor`}
                </pre>
                <button
                  type="button"
                  onClick={copyCommand}
                  className="absolute top-2 right-2 px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-xs rounded-lg border border-slate-600 transition-colors duration-200"
                >
                  {copied ? "✓ Copied!" : "Copy"}
                </button>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-4">
              <p className="font-semibold text-slate-50 mb-2">Step 4: Fill the Form</p>
              <p className="text-sm">
                Copy the output values (clientId, clientSecret, tenantId) into the form →
              </p>
            </div>
          </div>
        </div>

        {/* Right Column - Auth Form */}
        <div className="form-section">
          <h2 className="form-section-title">Azure Credentials</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {!isAuthorized && (
              <>
                <div>
                  <label htmlFor="azServicePrincipalID" className="form-label">
                    Client ID
                  </label>
                  <input
                    type="text"
                    id="azServicePrincipalID"
                    name="azServicePrincipalID"
                    value={formData.azServicePrincipalID}
                    onChange={handleChange}
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    className="form-input"
                    required
                  />
                </div>

                <div>
                  <label htmlFor="azServicePrincipalPassword" className="form-label">
                    Client Secret
                  </label>
                  <input
                    type="password"
                    id="azServicePrincipalPassword"
                    name="azServicePrincipalPassword"
                    value={formData.azServicePrincipalPassword}
                    onChange={handleChange}
                    placeholder="••••••••••••••••••••"
                    className="form-input"
                    required
                  />
                </div>

                <div>
                  <label htmlFor="azTenant" className="form-label">
                    Tenant ID
                  </label>
                  <input
                    type="text"
                    id="azTenant"
                    name="azTenant"
                    value={formData.azTenant}
                    onChange={handleChange}
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    className="form-input"
                    required
                  />
                </div>

                <div>
                  <label htmlFor="azSubscriptionID" className="form-label">
                    Subscription ID
                  </label>
                  <input
                    type="text"
                    id="azSubscriptionID"
                    name="azSubscriptionID"
                    value={formData.azSubscriptionID}
                    onChange={handleChange}
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    className="form-input"
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="btn-primary w-full py-3 flex items-center justify-center gap-2"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      <span>Connecting...</span>
                    </>
                  ) : (
                    "Connect to Azure"
                  )}
                </button>
              </>
            )}

            {responseMessage && (
              <div className="p-3 bg-red-900/30 border border-red-500 rounded-lg text-red-300 text-sm">
                {responseMessage}
              </div>
            )}

            {isAuthorized && (
              <div className="p-3 bg-green-900/30 border border-green-500 rounded-lg text-green-300 text-sm text-center">
                Successfully connected to Azure
              </div>
            )}
          </form>
        </div>
      </div>

      {/* Footer Note */}
      <div className="text-center text-slate-500 text-sm mt-6">
        <p>Your credentials are stored in memory for the current session and used only to manage Azure resources for this lab.</p>
      </div>
    </div>
  )
}
