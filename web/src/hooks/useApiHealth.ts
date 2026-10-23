/**
 * 查询服务健康检查 Hook（自 ChatPage 抽出，60s 轮询间隔可配置）。
 * Activity 隐藏时 effect 销毁、轮询暂停，恢复时重建（设计文档 §4.1 决策）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api/client";

export function useApiHealth(intervalMs: number): boolean {
  const [connected, setConnected] = useState(false);
  /** 上一次的健康检查结果：只在「已连接/不可用」变化时打日志，避免轮询刷屏 */
  const healthRef = useRef<boolean | null>(null);

  const checkHealth = useCallback(async () => {
    let ok = false;
    let failure: unknown = null;
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (!res.ok) throw new Error(`health 返回 ${res.status}`);
      ok = true;
    } catch (err) {
      failure = err;
    }
    if (healthRef.current !== ok) {
      healthRef.current = ok;
      if (ok) console.log("[chat] 查询服务已连接");
      else console.warn("[chat] 查询服务不可用", failure);
    }
    setConnected(ok);
  }, []);

  useEffect(() => {
    checkHealth();
    const timer = setInterval(checkHealth, intervalMs);
    return () => clearInterval(timer);
  }, [checkHealth, intervalMs]);

  return connected;
}
