"use client"
import { Fragment, useState } from "react"
import { Dialog, Transition } from "@headlessui/react"

interface DeleteScenarioModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  scenarioName: string
}

export default function DeleteScenarioModal({
  isOpen,
  onClose,
  onConfirm,
  scenarioName,
}: DeleteScenarioModalProps) {
  const [confirmText, setConfirmText] = useState("")
  const [error, setError] = useState("")

  const handleConfirm = () => {
    if (confirmText === scenarioName) {
      onConfirm()
      setConfirmText("")
      setError("")
    } else {
      setError("Scenario name does not match")
    }
  }

  const handleClose = () => {
    setConfirmText("")
    setError("")
    onClose()
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-10" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-base-100 p-6 text-left align-middle shadow-xl transition-all border-4 border-error">
                <Dialog.Title
                  as="h3"
                  className="text-lg font-medium leading-6 text-base-content"
                >
                  Delete Scenario
                </Dialog.Title>
                <div className="mt-2">
                  <p className="text-sm text-base-content/80">
                    Are you sure you want to delete <span className="font-bold text-error">{scenarioName}</span>?
                  </p>
                  <p className="text-sm text-base-content/80 mt-2">
                    This will permanently delete:
                  </p>
                  <ul className="text-sm text-base-content/80 list-disc list-inside ml-2 mt-1">
                    <li>Scenario configuration files</li>
                    <li>Bicep templates</li>
                    <li>VM snapshots from gallery</li>
                  </ul>
                  <p className="text-sm text-error font-semibold mt-3">
                    Type the scenario name to confirm:
                  </p>
                  <input
                    type="text"
                    className="mt-2 w-full px-3 py-2 bg-base-200 border border-base-300 rounded-lg text-base-content focus:outline-none focus:border-error"
                    placeholder={scenarioName}
                    value={confirmText}
                    onChange={(e) => {
                      setConfirmText(e.target.value)
                      setError("")
                    }}
                  />
                  {error && (
                    <p className="text-error text-sm mt-1">{error}</p>
                  )}
                </div>

                <div className="mt-4 flex gap-3 justify-end">
                  <button
                    type="button"
                    className="px-4 py-2 bg-base-200 text-base-content rounded-lg hover:bg-base-300 border border-base-300"
                    onClick={handleClose}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="px-4 py-2 bg-error text-error-content rounded-lg hover:bg-error/90 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={handleConfirm}
                    disabled={confirmText !== scenarioName}
                  >
                    Delete
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}
