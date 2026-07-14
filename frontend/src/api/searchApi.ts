import { api } from './client'

export interface SearchHit {
    id: string;
    type: string;
    title: string;
    subtitle?: string;
    url?: string;   // deep-link to navigate to (Slice 6)
}

export const globalSearch = async (
    accessToken: string,
    q: string,
    signal?: AbortSignal,
): Promise<SearchHit[]> => {
    const {data} = await api.get<SearchHit[]>('/search', {
        headers: { Authorization: `Bearer ${accessToken}` },
        params: { q},
        signal,
    });
    return data as SearchHit[];
}

// Slice 5: record which result the user picked. Fire-and-forget — a failed
// click log must never disrupt navigation, so callers ignore the result.
export const logSearchClick = async (
    accessToken: string,
    payload: { query: string; hit_id: string; hit_type: string; position?: number },
): Promise<void> => {
    try {
        await api.post('/search/click', payload, {
            headers: { Authorization: `Bearer ${accessToken}` },
        });
    } catch {
        /* best-effort telemetry; swallow errors */
    }
}
