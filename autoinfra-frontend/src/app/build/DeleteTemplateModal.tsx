"use client"
import { Fragment, useState } from "react"
import { Dialog, Transition } from "@headlessui/react"

interface DeleteTemplateModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  templateName: string
}

export default function DeleteTemplateModal({
  isOpen,
  onClose,
  onConfirm,
  templateName,
}: DeleteTemplateModalProps) {
  const [confirmText, setConfirmText] = useState("")
  const [error, setError] = useState("")

  const handleConfirm = () => {
    if (confirmText === templateName) {
      onConfirm()
      setConfirmText("")
      setError("")
    } else {
      setError("Template name does not match")
    }
  }

  const handleClose = () => {
    setConfirmText("")
    setError("")
    onClose()
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-neutral-900 p-6 text-left align-middle shadow-xl transition-all border-4 border-red-900">
                <Dialog.Title
                  as="h3"
                  className="text-lg font-medium leading-6 text-neutral-50"
                >
                  Delete Template
                </Dialog.Title>
                <div className="mt-2">
                  <p className="text-sm text-neutral-300">
                    Are you sure you want to delete <span className="font-bold text-red-400">{templateName}</span>?
                  </p>
                  <p className="text-sm text-neutral-300 mt-2">
                    This will permanently delete:
                  </p>
                  <ul className="text-sm text-neutral-300 list-disc list-inside ml-2 mt-1">
                    <li>Template configuration file</li>
                    <li>Saved topology settings</li>
                  </ul>
                  <p className="text-sm text-red-400 font-semibold mt-3">
                    Type the template name to confirm:
                  </p>
                  <input
                    type="text"
                    className="mt-2 w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-50 focus:outline-none focus:border-red-500"
                    placeholder={templateName}
                    value={confirmText}
                    onChange={(e) => {
                      setConfirmText(e.target.value)
                      setError("")
                    }}
                  />
                  {error && (
                    <p className="text-red-500 text-sm mt-1">{error}</p>
                  )}
                </div>

                <div className="mt-4 flex gap-3 justify-end">
                  <button
                    type="button"
                    className="px-4 py-2 bg-neutral-800 text-neutral-50 rounded-lg hover:bg-neutral-700 border border-neutral-700"
                    onClick={handleClose}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="px-4 py-2 bg-red-900 text-neutral-50 rounded-lg hover:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={handleConfirm}
                    disabled={confirmText !== templateName}
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
