class UrlHelper {
  static String normalizeDiscordWebhookUrl(String? url) {
    if (url == null || url.isEmpty) {
      return '';
    }
    
    //discordapp.com을 discord.com으로 변환
    return url.replaceAll(
      'https://discordapp.com/api/webhooks/', 
      'https://discord.com/api/webhooks/',
    );
  }
  
  // URL이 Discord Webhook URL 형식인지 검증
  static bool isDiscordWebhookUrl(String url) {
    return url.startsWith('https://discord.com/api/webhooks/') || 
           url.startsWith('https://discordapp.com/api/webhooks/');
  }
  
  // URL 정리 (앞뒤 공백 제거)
  static String cleanUrl(String url) {
    return url.trim();
  }
}