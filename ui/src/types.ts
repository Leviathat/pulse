export interface Monitor {
  id: string;
  name: string;
  keywords: string[];
  created_at: string;
}

export interface Article {
  id: string;
  source: string;
  source_id: string;
  url: string;
  title: string;
  body: string;
  author: string;
  published_at: string;
  fetched_at: string;
  lang?: string;
  matched_monitor_ids?: string[];
}

export interface SearchResponse {
  total: number;
  limit: number;
  offset: number;
  results: Article[];
}

export interface TimelinePoint {
  time: string;
  count: number;
}

export interface Timeline {
  monitor_id: string;
  interval: string;
  points: TimelinePoint[];
  cached: boolean;
}
