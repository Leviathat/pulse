import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type { Monitor, SearchResponse, Timeline } from "./types";

// baseUrl "/api" is proxied to the API service by nginx (prod) or Vite (dev).
export const api = createApi({
  reducerPath: "api",
  baseQuery: fetchBaseQuery({ baseUrl: "/api" }),
  tagTypes: ["Monitor"],
  endpoints: (build) => ({
    getMonitors: build.query<Monitor[], void>({
      query: () => "/monitors",
      providesTags: ["Monitor"],
    }),
    createMonitor: build.mutation<Monitor, { name: string; keywords: string[] }>({
      query: (body) => ({ url: "/monitors", method: "POST", body }),
      invalidatesTags: ["Monitor"],
    }),
    deleteMonitor: build.mutation<void, string>({
      query: (id) => ({ url: `/monitors/${id}`, method: "DELETE" }),
      invalidatesTags: ["Monitor"],
    }),
    getFeed: build.query<SearchResponse, { id: string; limit?: number }>({
      query: ({ id, limit = 30 }) => `/monitors/${id}/feed?limit=${limit}`,
    }),
    getTimeline: build.query<Timeline, { id: string; interval?: string }>({
      query: ({ id, interval = "1h" }) =>
        `/monitors/${id}/timeline?interval=${interval}`,
    }),
    search: build.query<SearchResponse, { q: string; limit?: number }>({
      query: ({ q, limit = 30 }) =>
        `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    }),
  }),
});

export const {
  useGetMonitorsQuery,
  useCreateMonitorMutation,
  useDeleteMonitorMutation,
  useGetFeedQuery,
  useGetTimelineQuery,
  useLazySearchQuery,
} = api;
