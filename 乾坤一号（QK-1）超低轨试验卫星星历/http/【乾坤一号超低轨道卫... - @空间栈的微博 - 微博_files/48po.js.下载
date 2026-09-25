try {
  var endpoint = 'https://weibo.com/ajax/log/rum';

  function getCookie(cookieName) {
    var strCookie = document.cookie;
    var cookieList = strCookie.split(';');
    for (var i = 0; i < cookieList.length; i++) {
      var arr = cookieList[i].split('=');
      if (cookieName === arr[0].trim()) {
        return arr[1];
      }
    }
    return '';
  }

  var pathList = [
    'https://picupload.weibo.com/interface/upload.php',
    'https://weibo.com/ajax/statuses/buildComments',
    'https://weibo.com/ajax/feed/unreadfriendstimeline',
    'https://weibo.com/ajax/statuses/update',
    'https://weibo.com/ajax/comments/create',
    'https://weibo.com/ajax/statuses/mymblog',
    'https://weibo.com/ajax/statuses/show',
    'https://weibo.com/ajax/statuses/setLike',
    'https://weibo.com/ajax/statuses/normal_repost',
    'https://image.api.weibo.com/interface/upload.php'
  ];

  function checkPath(path) {
    return pathList.some(function (item) {
      return path.indexOf(item) === 0;
    });
  }

  function getQueryVariable(url, variable) {
    try {
      if (!url || (url && !url.startsWith('http'))) {
        return '';
      }
      var query = new URL(url).search.substring(1);
      var vars = query.split('&');
      for (var i = 0; i < vars.length; i++) {
        var pair = vars[i].split('=');
        if (pair[0] == variable) {
          return pair[1];
        }
      }
    } catch (e) {
      console.log(e);
    }
    return '';
  }

  function sendLog(entry = {}) {
    var rumData = new FormData();
    rumData.append('entry', JSON.stringify(entry));
    rumData.append('request_id', getQueryVariable(entry.name, 'request_id'));

    fetch(endpoint, {
      keepalive: true,
      method: 'POST',
      headers: {
        // 'Content-Type': 'application/x-www-form-urlencoded',
        'X-Xsrf-Token': getCookie('XSRF-TOKEN')
      },
      body: rumData
    });
  }

  var po = new PerformanceObserver(function (list) {
    for (var entry of list.getEntries()) {
      // If transferSize is 0, the resource was fulfilled via the cache.
      // console.log(entry.name, entry.transferSize === 0, entry);
      switch (entry.entryType) {
        case 'resource': {
          if (
            checkPath(entry.name) &&
            entry.initiatorType === 'xmlhttprequest'
          ) {
            console.log(entry);
            var r0 = entry,
              loadtime = r0.duration;
            var dns, tcp, ttfb, ssl;

            if (r0.requestStart) {
              (dns = r0.domainLookupEnd - r0.domainLookupStart),
                (tcp = r0.connectEnd - r0.connectStart),
                (ttfb = r0.responseStart - r0.requestStart);

              if (r0.secureConnectionStart) {
                ssl = r0.connectEnd - r0.secureConnectionStart;
              }
              console.log(
                `DNS: ${dns}ms, TCP: ${tcp}ms, TTFB: ${ttfb}ms, SSL: ${ssl}ms`
              );

              var fileSize = getQueryVariable(entry.name, 'file_size') || 0;

              var formData = JSON.parse(JSON.stringify(entry));

              formData.dns = dns;
              formData.tcp = tcp;
              formData.ttfb = ttfb;
              try {
                var urlObj = new URL(entry.name);
                formData.pathname = urlObj.origin + urlObj.pathname;
              } catch (e) {
                console.log(e);
              }
              if (r0.duration !== 0) {
                formData.speed = fileSize / r0.duration;
              }

              sendLog(formData);
            }
          }
          return;
        }
        case 'mark': {
          var formData = {
            duration: entry.duration,
            entryType: entry.entryType,
            name: entry.name,
            startTime: entry.startTime
          };
          if (entry && entry.detail && typeof entry.detail === 'object') {
            formData = Object.assign({}, formData, entry.detail);
          }

          if (['imageUpload'].includes(entry.name)) {
            console.log(entry);
            sendLog(formData);
          }
        }
      }
    }
  });
  // Start listening for `resource` entries to be dispatched.
  po.observe({ entryTypes: ['mark', 'resource'], buffered: true });
} catch (e) {
  // Do nothing if the browser doesn't support this API.
}
