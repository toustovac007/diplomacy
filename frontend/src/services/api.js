import axios from "axios";

// Discard shared legacy credentials; each tab must establish its own session.
localStorage.removeItem("access_token");
localStorage.removeItem("refresh_token");

const api = axios.create({
    baseURL: "http://127.0.0.1:8000/api/",
});


// Přidání access tokenu ke každému requestu
api.interceptors.request.use(
    (config) => {
        const token = sessionStorage.getItem("access_token");

        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        } else {
            delete config.headers.Authorization;
        }

        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);


// Pokud access token vyprší, pokusíme se ho obnovit
api.interceptors.response.use(
    (response) => response,

    async (error) => {
        const originalRequest = error.config;

        if (
            error.response?.status === 401 &&
            !originalRequest._retry
        ) {
            originalRequest._retry = true;

            const refreshToken =
                sessionStorage.getItem("refresh_token");

            if (!refreshToken) {
                return Promise.reject(error);
            }

            try {
                const response = await axios.post(
                    "http://127.0.0.1:8000/api/token/refresh/",
                    {
                        refresh: refreshToken,
                    }
                );

                const newAccessToken = response.data.access;

                if (sessionStorage.getItem("refresh_token") !== refreshToken) {
                    return Promise.reject(error);
                }

                sessionStorage.setItem(
                    "access_token",
                    newAccessToken
                );

                originalRequest.headers.Authorization =
                    `Bearer ${newAccessToken}`;

                return api(originalRequest);

            } catch (refreshError) {

                if (sessionStorage.getItem("refresh_token") !== refreshToken) {
                    return Promise.reject(refreshError);
                }

                sessionStorage.removeItem("access_token");
                sessionStorage.removeItem("refresh_token");

                // Obnovení stránky vrátí uživatele na login
                window.location.reload();

                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

export default api;
