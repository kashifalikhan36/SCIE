import { create } from "zustand";

interface LiveState {
  isConnected: boolean;
  meetingId: string | null;
  ranking: any; // Ideally typed with RankingResult
  participants: Record<string, any>; // participant_id -> ParticipantState
  logs: any[];
  setConnectionStatus: (status: boolean) => void;
  setMeetingId: (id: string) => void;
  updateLiveState: (data: any) => void;
  addLog: (log: any) => void;
  clearState: () => void;
}

export const useLiveStore = create<LiveState>((set) => ({
  isConnected: false,
  meetingId: null,
  ranking: null,
  participants: {},
  logs: [],
  setConnectionStatus: (status) => set({ isConnected: status }),
  setMeetingId: (id) => set({ meetingId: id }),
  updateLiveState: (data) =>
    set((state) => ({
      ranking: data.ranking || state.ranking,
      participants: data.participants || state.participants,
    })),
  addLog: (log) =>
    set((state) => ({
      logs: [...state.logs, log].slice(-100), // Keep last 100 logs
    })),
  clearState: () =>
    set({
      isConnected: false,
      meetingId: null,
      ranking: null,
      participants: {},
      logs: [],
    }),
}));
