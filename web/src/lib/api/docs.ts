/** 文档管理页 API (后端方案 §4 / §5 / §6) */

import { request } from "./client";
import type {
  DocsDeleteResponse,
  DocsDetailResponse,
  DocsListResponse,
} from "@/types/docs";

/** 文档列表 (分页, 按 id 降序) */
export async function getDocsList(
  offset = 0,
  limit = 100,
): Promise<DocsListResponse> {
  const res = await request(`/api/docs?offset=${offset}&limit=${limit}`);
  return await res.json();
}

/** 文档详情 (markdown 原文 / 切块 / keywords / abstract) */
export async function getDocsDetail(docId: string): Promise<DocsDetailResponse> {
  const res = await request(`/api/docs/${encodeURIComponent(docId)}`);
  return await res.json();
}

/** 删除文档 (级联删除 Milvus docs/chunks 与 MinIO 制品) */
export async function deleteDoc(docId: string): Promise<DocsDeleteResponse> {
  const res = await request(`/api/docs/${encodeURIComponent(docId)}`, {
    method: "DELETE",
  });
  return await res.json();
}
