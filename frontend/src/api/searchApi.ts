import { api } from './client'

export interface SearchHit {
    id: string;
    type: string;
    title: string;
    subtitle?: string;
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