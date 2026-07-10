import axios from "axios";
import { QueryClient } from "@tanstack/react-query";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// React Query Client
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  },
});

// Dashboard APIs
export const fetchMeetings = async () => {
  const { data } = await api.get("/dashboard/meetings");
  return data;
};

export const deleteMeeting = async (meetingId: string) => {
  const { data } = await api.delete(`/dashboard/meetings/${meetingId}`);
  return data;
};

export const fetchMeetingSummary = async (meetingId: string) => {
  const { data } = await api.get(`/dashboard/meetings/${meetingId}`);
  return data;
};

export const fetchMeetingParticipants = async (meetingId: string) => {
  const { data } = await api.get(`/dashboard/meetings/${meetingId}/participants`);
  return data;
};

export const fetchMeetingTimeline = async (meetingId: string) => {
  const { data } = await api.get(`/dashboard/meetings/${meetingId}/timeline`);
  return data;
};

export const fetchMeetingAnalytics = async (meetingId: string) => {
  const { data } = await api.get(`/dashboard/meetings/${meetingId}/analytics`);
  return data;
};

export const fetchDashboardStats = async () => {
  const { data } = await api.get("/dashboard/stats");
  return data;
};

