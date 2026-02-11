"use client"

import { useAuth } from "@/contexts/AuthContext"

export default function AzureStatus() {
  const { isAuthenticated, isLoading } = useAuth()

  return (
    <div className="card-container w-fit min-w-[10rem] px-3 py-2">
      <div className="flex items-center justify-center gap-1.5">
        <span className="base-text-color text-xs font-semibold">Azure</span>
        {isLoading ? (
          <div className="azure-status-indicator-loading" />
        ) : (
          <div
            className={
              isAuthenticated
                ? "azure-status-indicator-green"
                : "azure-status-indicator-red"
            }
          />
        )}
      </div>
    </div>
  )
}
