import { useCallback, useEffect, useState } from "react";

import { apiGet } from "../api/client";

export function useApi(path, params = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [requestKey, setRequestKey] = useState(0);
  const paramsKey = JSON.stringify(params);

  const retry = useCallback(() => {
    setRequestKey((key) => key + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setError(null);

    apiGet(path, JSON.parse(paramsKey), controller.signal)
      .then((result) => {
        if (active) {
          setData(result);
        }
      })
      .catch((requestError) => {
        if (active && requestError?.name !== "AbortError") {
          setError(requestError);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [path, paramsKey, requestKey]);

  return { data, loading, error, retry };
}
