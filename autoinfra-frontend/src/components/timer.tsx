import React, { useState, useEffect } from "react";

function Timer({ timeout, onTimerExpired }) {
  const [seconds, setSeconds] = useState(
    Math.floor(timeout - Date.now() / 1000)
  );
  const [hasExpired, setHasExpired] = useState(false);

  useEffect(() => {
    setSeconds(Math.floor(timeout - Date.now() / 1000));
    setHasExpired(false);
  }, [timeout]);

  useEffect(() => {
    const interval = setInterval(() => {
      setSeconds((prevSeconds) => prevSeconds - 1);
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Only trigger onTimerExpired if:
    // 1. Timer actually counted down to 0 (not starting at 0 or negative)
    // 2. We haven't already expired
    if (seconds <= 0 && !hasExpired) {
      // Only call if the initial timeout was valid (in the future)
      const initialSeconds = Math.floor(timeout - Date.now() / 1000);
      if (initialSeconds > 0) {
        setHasExpired(true);
        onTimerExpired();
      }
    }
    // adding [seconds] here makes the useEffect depend on
    // the 'seconds' state, triggering when that state changes
  }, [seconds, onTimerExpired, hasExpired, timeout]);

  function formatTime(seconds: number) {
    const h = Math.floor(seconds / 3600)
      .toString()
      .padStart(2, "0");
    const m = Math.floor((seconds % 3600) / 60)
      .toString()
      .padStart(2, "0");
    const s = Math.floor(seconds % 60)
      .toString()
      .padStart(2, "0");
    return h + ":" + m + ":" + s;
  }

  return <div>{formatTime(seconds)}</div>;
}

export default Timer;
