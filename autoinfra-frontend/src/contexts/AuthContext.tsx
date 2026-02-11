"use client"
import React, { createContext, useContext, useState, useEffect, ReactNode } from "react"
import GlobalConfigs from "../app/app.config"

// Types
interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  refreshAuth: () => Promise<void>
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Provider component
export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Fetch auth status
  const checkAuth = async () => {
    try {
      const response = await fetch(GlobalConfigs.checkAuthEndpoint)
      const data = await response.json()
      setIsAuthenticated(data.message === "Authorized")
    } catch (error) {
      console.error("[AuthContext] Error checking auth:", error)
      setIsAuthenticated(false)
    } finally {
      setIsLoading(false)
    }
  }

  // Initial check on mount
  useEffect(() => {
    checkAuth()
  }, [])

  // Re-check auth when window regains focus (detects backend restarts/credential expiry)
  // Pattern: "Check on focus when you DON'T expect change" (passive state)
  useEffect(() => {
    const handleFocus = () => {
      checkAuth()
    }

    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [])

  // Manual refresh function
  const refreshAuth = async () => {
    await checkAuth()
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        refreshAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// Custom hook to use the context
export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
