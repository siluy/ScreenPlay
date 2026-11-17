// The existing pages.dev hostname is the single browser origin.
export default {
  async fetch(request, env) {
    return env.STUDY_GATEWAY.fetch(request);
  }
};
